# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""HTTP server: token, Host and Origin checks, static files, jobs over SSE."""

import http.client
import json
import threading
import time

import pytest

from netpulse import validators as v
from netpulse.config import Settings
from netpulse.history import History
from netpulse.server import App
from netpulse.tools.base import Tool


def _echo_validate(params):
    return {"host": v.host_or_ip(params.get("host"))}


def _echo_run(ctx, params):
    r = ctx.run(["echo", params["host"]], timeout=5)
    return {"status": "ok", "exit_code": r.returncode}


def _slow_run(ctx, params):
    r = ctx.run(["sleep", "300"], timeout=60)
    return {"exit_code": r.returncode}


ECHO = Tool("echo", "Echo", "Utilities", "test", _echo_validate, _echo_run, lambda p: 5)
SLOW = Tool("slow", "Slow", "Utilities", "test", _echo_validate, _slow_run, lambda p: 60)


@pytest.fixture
def app(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>t</title>")
    (static / "secret.txt").write_text("nope")
    (tmp_path / "outside.html").write_text("outside")
    a = App(
        {"echo": ECHO, "slow": SLOW},
        settings=Settings(tmp_path / "settings.json"),
        history=History(tmp_path / "history.jsonl"),
        static_dir=static,
    )
    t = threading.Thread(target=a.serve_forever, daemon=True)
    t.start()
    yield a
    a.manager.shutdown()
    a.httpd.shutdown()
    a.httpd.server_close()


def request(app, method, path, body=None, headers=None, token=True, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
    hdrs = {"Host": f"127.0.0.1:{app.port}" if host is None else host}
    if token:
        hdrs["X-NetPulse-Token"] = app.token
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = raw.decode()
    return resp.status, payload, resp


def test_refuses_non_loopback(tmp_path):
    with pytest.raises(ValueError, match="non-loopback"):
        App({}, bind="0.0.0.0", settings=Settings(tmp_path / "s.json"))


def test_binds_loopback_random_port(app):
    assert app.httpd.server_address[0] == "127.0.0.1"
    assert app.port > 1024


def test_api_requires_token(app):
    assert request(app, "GET", "/api/info", token=False)[0] == 401
    assert (
        request(app, "GET", "/api/info", headers={"X-NetPulse-Token": "wrong"}, token=False)[0]
        == 401
    )
    assert request(app, "GET", f"/api/info?token={app.token}", token=False)[0] == 401
    status, data, _ = request(app, "GET", "/api/info")
    assert status == 200 and data["name"] == "NetPulse"


def test_token_in_query_only_for_sse(app):
    status, job, _ = request(
        app, "POST", "/api/jobs", {"tool": "echo", "params": {"host": "x.org"}}
    )
    assert status == 201
    path = f"/api/jobs/{job['id']}/events?token={app.token}"
    status, body, resp = request(app, "GET", path, token=False)
    assert status == 200
    assert resp.getheader("Content-Type").startswith("text/event-stream")
    assert "event: end" in body


@pytest.mark.parametrize(
    "host", ["evil.com", "evil.com:{port}", "127.0.0.1:1", "attacker.localhost:{port}", ""]
)
def test_bad_host_header_blocked(app, host):
    status, _, _ = request(app, "GET", "/", host=host.format(port=app.port))
    assert status == 403
    status, _, _ = request(app, "GET", "/api/info", host=host.format(port=app.port))
    assert status == 403


def test_localhost_host_header_ok(app):
    assert request(app, "GET", "/", host=f"localhost:{app.port}")[0] == 200


@pytest.mark.parametrize("origin", ["http://evil.com", "null", "https://127.0.0.1:{port}"])
def test_foreign_origin_blocked(app, origin):
    hdr = {"Origin": origin.format(port=app.port)}
    assert request(app, "GET", "/api/info", headers=hdr)[0] == 403
    status, _, _ = request(
        app, "POST", "/api/jobs", {"tool": "echo", "params": {"host": "x.org"}}, headers=hdr
    )
    assert status == 403


def test_cross_site_fetch_metadata_blocked(app):
    hdr = {"Sec-Fetch-Site": "cross-site"}
    assert request(app, "GET", "/api/info", headers=hdr)[0] == 403
    hdr = {"Sec-Fetch-Site": "same-origin", "Origin": f"http://127.0.0.1:{app.port}"}
    assert request(app, "GET", "/api/info", headers=hdr)[0] == 200


def test_post_requires_json_content_type(app):
    conn = http.client.HTTPConnection("127.0.0.1", app.port)
    conn.request(
        "POST",
        "/api/jobs",
        body=b"tool=echo",
        headers={
            "Host": f"127.0.0.1:{app.port}",
            "X-NetPulse-Token": app.token,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    assert conn.getresponse().status == 415


def test_security_headers_on_static(app):
    status, _, resp = request(app, "GET", "/", token=False)
    assert status == 200
    csp = resp.getheader("Content-Security-Policy")
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert resp.getheader("X-Frame-Options") == "DENY"


@pytest.mark.parametrize(
    "path", ["/../outside.html", "/%2e%2e/outside.html", "/secret.txt", "/nope.js", "/static/../x"]
)
def test_static_traversal_and_unknown_types(app, path):
    assert request(app, "GET", path, token=False)[0] == 404


def test_validation_error_is_400(app):
    status, data, _ = request(
        app, "POST", "/api/jobs", {"tool": "echo", "params": {"host": "$(id)"}}
    )
    assert status == 400
    assert data["field"] == "host"
    status, data, _ = request(app, "POST", "/api/jobs", {"tool": "nope", "params": {}})
    assert status == 400


def test_job_runs_and_goes_to_history(app):
    status, job, _ = request(
        app, "POST", "/api/jobs", {"tool": "echo", "params": {"host": "bücher.de"}}
    )
    assert status == 201
    assert job["params"]["host"] == "xn--bcher-kva.de"
    events = request(app, "GET", f"/api/jobs/{job['id']}/events")[1]
    assert "xn--bcher-kva.de" in events
    status, full, _ = request(app, "GET", f"/api/jobs/{job['id']}")
    assert full["status"] == "done" and "xn--bcher-kva.de" in full["output"]
    entries = request(app, "GET", "/api/history")[1]["entries"]
    assert entries and entries[0]["id"] == job["id"]
    assert request(app, "GET", f"/api/history/{job['id']}")[1]["output"]
    assert request(app, "DELETE", "/api/history")[0] == 200
    assert request(app, "GET", "/api/history")[1]["entries"] == []


def test_cancel_over_api(app):
    status, job, _ = request(
        app, "POST", "/api/jobs", {"tool": "slow", "params": {"host": "x.org"}}
    )
    assert status == 201
    app.manager.subscribe(app.manager.get(job["id"]))
    time.sleep(0.2)
    assert request(app, "DELETE", f"/api/jobs/{job['id']}")[0] == 200
    events = request(app, "GET", f"/api/jobs/{job['id']}/events")[1]
    assert '"status":"cancelled"' in events


def test_settings_roundtrip(app):
    status, data, _ = request(app, "PUT", "/api/settings", {"theme": "dark", "history_max": 50})
    assert status == 200 and data["theme"] == "dark" and data["history_max"] == 50
    assert request(app, "PUT", "/api/settings", {"theme": "neon"})[0] == 400
    assert request(app, "GET", "/api/settings")[1]["theme"] == "dark"


def test_body_size_limit(app):
    status, _, _ = request(app, "POST", "/api/jobs", {"tool": "echo", "params": {"x": "a" * 70000}})
    assert status == 413


def test_idle_watch_stops_only_after_a_client_went_away(app):
    import time as _t

    from netpulse.server import start_idle_watch

    fired = []
    start_idle_watch(app, 0.2, lambda: fired.append(1), interval=0.05)
    _t.sleep(0.4)
    assert fired == []  # no page has connected yet: keep waiting
    request(app, "GET", "/api/info")  # a page connects…
    _t.sleep(0.6)  # …and goes quiet
    assert fired == [1]
