# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Command line, window detection and whole-process shutdown."""

import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from netpulse import __main__ as cli
from netpulse import window

SRC = Path(__file__).resolve().parent.parent / "src"


def test_parse_args_defaults():
    args = cli.parse_args([])
    assert (args.port, args.bind, args.browser, args.no_open) == (0, "127.0.0.1", False, False)


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "192.168.1.10", "example.com"])
def test_refuses_non_loopback_bind(bind, capsys):
    with pytest.raises(SystemExit):
        cli.parse_args(["--bind", bind])
    assert "non-loopback" in capsys.readouterr().err


def test_bad_port_and_exclusive_modes():
    with pytest.raises(SystemExit):
        cli.parse_args(["--port", "70000"])
    with pytest.raises(SystemExit):
        cli.parse_args(["--browser", "--no-open"])


def test_choose_mode(monkeypatch):
    assert cli.choose_mode(cli.parse_args(["--no-open"])) == "none"
    assert cli.choose_mode(cli.parse_args(["--browser"])) == "browser"
    monkeypatch.setattr(window, "available", lambda: False)
    assert cli.choose_mode(cli.parse_args([])) == "browser"
    monkeypatch.setattr(window, "available", lambda: True)
    assert cli.choose_mode(cli.parse_args([])) == "window"


def test_window_needs_a_display(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert window.available() is False


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        cli.parse_args(["--version"])
    assert capsys.readouterr().out.startswith("netpulse ")


def _api(base, token, method, path, body=None):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-NetPulse-Token": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _children(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
    return [int(x) for x in out.split()]


def _ping_works() -> bool:
    """ping exists *and* may send packets (not always true in containers)."""
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "1", "127.0.0.1"], capture_output=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


@pytest.mark.skipif(not _ping_works(), reason="needs a working ping")
def test_sigterm_stops_server_and_kills_running_jobs(tmp_path):
    env = {
        **os.environ,
        "PYTHONPATH": str(SRC),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_RUNTIME_DIR": str(tmp_path / "run"),
    }
    (tmp_path / "run").mkdir(mode=0o700)
    proc = subprocess.Popen(
        [sys.executable, "-m", "netpulse", "--no-open"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        url = token = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if m := re.search(r"(http://127\.0\.0\.1:\d+/)#token=(\S+)", line):
                url, token = m.group(1), m.group(2)
                break
        assert url, "server did not start"
        job = _api(
            url,
            token,
            "POST",
            "/api/jobs",
            {"tool": "ping", "params": {"host": "127.0.0.1", "count": 100}},
        )
        # keep it "subscribed" long enough: an unclaimed job would be cancelled after 20 s anyway
        time.sleep(1.0)
        pings = [p for p in _children(proc.pid)]
        assert pings, "ping child not started"
        assert _api(url, token, "GET", f"/api/jobs/{job['id']}")["status"] == "running"
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=10) == 0
        for pid in pings:
            assert not Path(f"/proc/{pid}").exists(), f"child {pid} survived"
        assert not (tmp_path / "run" / "netpulse" / "instance.json").exists()
        history = (tmp_path / "data" / "netpulse" / "history.jsonl").read_text()
        assert '"status":"cancelled"' in history
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
