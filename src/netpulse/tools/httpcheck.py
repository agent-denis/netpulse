# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""HTTP(S) check with curl: status, redirect chain, headers and a timing breakdown."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from netpulse import validators as v
from netpulse.tools.base import Params, Summary, Tool, command_runner

MARKER = "--- NetPulse timing ---"
VARIABLES = (
    "http_code", "http_version", "num_redirects", "remote_ip", "remote_port", "scheme",
    "ssl_verify_result", "url_effective", "time_namelookup", "time_connect", "time_appconnect",
    "time_pretransfer", "time_starttransfer", "time_redirect", "time_total", "size_download",
    "size_header", "speed_download", "content_type", "exitcode", "errormsg",
)  # fmt: skip
WRITE_OUT = "\n" + MARKER + "\n" + "".join(f"{k}=%{{{k}}}\n" for k in VARIABLES)
METHODS = ("GET", "HEAD")
FAMILIES = ("auto", "4", "6")
_STATUS_RE = re.compile(r"^HTTP/(\S+) (\d{3})(?: (.*))?$")


def validate(params: Params) -> Params:
    return {
        "url": v.url(params.get("url"), "url"),
        "method": v.choice(params.get("method"), METHODS, "method", default="GET"),
        "follow": v.boolean(params.get("follow"), "follow", default=True),
        "max_redirects": v.int_range(
            params.get("max_redirects"), 0, 20, "max_redirects", default=10
        ),
        "timeout": v.int_range(params.get("timeout"), 1, 120, "timeout", default=20),
        "insecure": v.boolean(params.get("insecure"), "insecure", default=False),
        "family": v.choice(params.get("family"), FAMILIES, "family", default="auto"),
    }


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    # -q must come first: it stops curl from reading ~/.curlrc.
    argv = ["curl", "-q", "--silent", "--show-error", "--output", "/dev/null", "--dump-header", "-"]
    argv += ["--proto", "=http,https", "--proto-redir", "=http,https"]
    argv += ["--max-time", str(p["timeout"]), "--write-out", WRITE_OUT]
    if p["method"] == "HEAD":
        argv.append("--head")
    if p["follow"]:
        argv += ["--location", "--max-redirs", str(p["max_redirects"])]
    if p["insecure"]:
        argv.append("--insecure")
    if p["family"] != "auto":
        argv.append(f"-{p['family']}")
    # --url marks the URL explicitly; it can never be read as an option.
    return [*argv, "--url", p["url"]]


def timeout(params: Params) -> float:
    return params["timeout"] + 10


def _float(value: str | None) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def timing(t: dict[str, str]) -> dict[str, Any]:
    """Split curl's timers into phases (ms).

    curl adds up its per-phase timers over every request of a redirect chain,
    so a DNS/connect/TLS breakdown is only exact for a single request. With
    redirects we show "Redirects" and "Final request" instead.
    """
    redirect = _float(t.get("time_redirect"))
    dns = _float(t.get("time_namelookup"))
    connect = _float(t.get("time_connect"))
    tls = _float(t.get("time_appconnect"))
    start = _float(t.get("time_starttransfer"))
    total = _float(t.get("time_total"))
    redirects = int(_float(t.get("num_redirects")))
    failed = (t.get("exitcode") or "0") != "0"
    if failed:
        phases: list[tuple[str, float]] = []
    elif redirects:
        phases = [(f"Redirects ({redirects})", redirect), ("Final request", total - redirect)]
    else:
        ready = tls if tls > 0 else connect
        phases = [
            ("DNS", dns),
            ("Connect", connect - dns),
            ("TLS", tls - connect if tls > 0 else 0.0),
            ("Server wait", start - ready if start else 0.0),
            ("Transfer", total - start if start else 0.0),
        ]
    return {
        "phases": [
            {"label": k, "ms": round(max(0.0, val) * 1000, 1)} for k, val in phases if val > 0
        ],
        "exact": not redirects,
        "ttfb_ms": round(start * 1000, 1),
        "total_ms": round(total * 1000, 1),
    }


def parse(output: str) -> Summary:
    head, _, tail = output.partition(MARKER)
    values: dict[str, str] = {}
    for line in tail.splitlines():
        key, sep, val = line.partition("=")
        if sep and key in VARIABLES:
            values[key] = val.strip()
    responses: list[dict[str, Any]] = []
    errors: list[str] = []
    current: dict[str, Any] | None = None
    for raw in head.splitlines():
        line = raw.rstrip("\r")
        if m := _STATUS_RE.match(line):
            current = {"http_version": m.group(1), "status": int(m.group(2)),
                       "reason": (m.group(3) or "").strip(), "headers": []}  # fmt: skip
            responses.append(current)
        elif line.startswith("curl: ("):
            errors.append(line[len("curl: ") :])
        elif current is not None and ":" in line and not line.startswith(" "):
            name, _, value = line.partition(":")
            current["headers"].append([name.strip(), value.strip()])
    for resp in responses:
        resp["location"] = next((v for k, v in resp["headers"] if k.lower() == "location"), None)
    code = int(values.get("http_code") or 0)
    summary: Summary = {
        "http_code": code,
        "http_version": values.get("http_version"),
        "url_effective": values.get("url_effective"),
        "remote_ip": values.get("remote_ip"),
        "remote_port": values.get("remote_port"),
        "num_redirects": int(values.get("num_redirects") or 0),
        "ssl_verify_result": values.get("ssl_verify_result"),
        "content_type": values.get("content_type"),
        "size_download": int(_float(values.get("size_download"))),
        "responses": responses,
        "headers": responses[-1]["headers"] if responses else [],
        "timing": timing(values),
        "errors": errors,
        "curl_exit": int(values.get("exitcode") or 0),
    }
    if errors or not code:
        msg = "; ".join(errors) or values.get("errormsg") or "no HTTP response"
        summary["status"], summary["message"] = "error", msg
    elif code >= 500:
        summary["status"], summary["message"] = "error", f"HTTP {code} (server error)"
    elif code >= 400:
        summary["status"], summary["message"] = "warning", f"HTTP {code} (client error)"
    elif 300 <= code < 400:
        summary["status"], summary["message"] = "warning", f"HTTP {code} (redirect not followed)"
    else:
        reason = responses[-1]["reason"] if responses and responses[-1]["reason"] else ""
        summary["status"] = "ok"
        summary["message"] = (
            f"HTTP {code}{' ' + reason if reason else ''} in {summary['timing']['total_ms']:.0f} ms"
        )
    return summary


def _first_url_fix(summary: Summary, url: str) -> Summary:
    """Fill in absolute URLs for the redirect chain, starting from the requested URL."""
    current = url
    for resp in summary.get("responses", []):
        resp["url"] = current
        if resp.get("location"):
            current = urljoin(current, resp["location"])
    return summary


def make_runner() -> Any:
    base = command_runner(build_argv, parse, timeout)

    def run(ctx: Any, params: Params) -> Summary:
        return _first_url_fix(base(ctx, params), params["url"])

    return run


TOOL = Tool(
    name="httpcheck",
    title="HTTP(S) check",
    group="Web & TLS",
    description="Fetch a URL and show the status, redirects, headers and where the time went.",
    validate=validate,
    run=make_runner(),
    timeout=timeout,
    binaries=("curl",),
    target=lambda p: p["url"],
)
