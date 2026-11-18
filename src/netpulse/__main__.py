# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Command-line entry point (``netpulse``)."""

from __future__ import annotations

import argparse
import contextlib
import shutil
import signal
import subprocess
import sys
import threading
from types import FrameType

from netpulse import __version__, security, tools
from netpulse.instance import InstanceLock, ask_running_instance
from netpulse.jobs import child_env
from netpulse.server import App, start_idle_watch

BROWSER_IDLE_TIMEOUT_S = 120.0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="netpulse",
        description="NetPulse: local network diagnostics (ping, traceroute, DNS, HTTP, TLS…).",
    )
    parser.add_argument("--version", action="version", version=f"netpulse {__version__}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--browser", action="store_true", help="open in the default web browser")
    mode.add_argument("--no-open", action="store_true", help="only print the URL")
    parser.add_argument("--port", type=int, default=0, help="port to listen on (default: random)")
    parser.add_argument(
        "--bind", default="127.0.0.1", help="loopback address to bind (default: 127.0.0.1)"
    )
    parser.add_argument("--debug", action="store_true", help="log requests to stderr")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if not security.is_loopback(args.bind):
        parser.error(f"refusing to bind to non-loopback address {args.bind!r}")
    return args


def open_browser(url: str) -> bool:
    opener = shutil.which("xdg-open")
    if opener is None:
        return False
    try:
        subprocess.Popen(
            [opener, url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={**child_env(), **_desktop_env()},
        )
    except OSError:
        return False
    return True


def _desktop_env() -> dict[str, str]:
    import os

    keys = (
        "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
        "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS",
        "BROWSER", "LANG", "LC_ALL",
    )  # fmt: skip
    return {k: os.environ[k] for k in keys if k in os.environ}


def choose_mode(args: argparse.Namespace) -> str:
    if args.no_open:
        return "none"
    if args.browser:
        return "browser"
    from netpulse import window

    return "window" if window.available() else "browser"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode = choose_mode(args)

    lock = InstanceLock()
    if not lock.acquire():
        info = lock.read() or {}
        reply = ask_running_instance(info)
        if reply is None:
            print("netpulse: another instance is running but not responding", file=sys.stderr)
            return 1
        launch = f"{info['url']}#token={info['token']}"
        if reply.get("window"):
            print("netpulse: raised the running NetPulse window")
        elif mode == "none":
            print(launch)
        else:
            open_browser(launch)
            print(f"netpulse: already running at {info['url']}")
        return 0

    try:
        app = App(tools.load_all(), bind=args.bind, port=args.port)
    except OSError as exc:
        print(f"netpulse: cannot listen on {args.bind}:{args.port}: {exc}", file=sys.stderr)
        lock.release()
        return 1
    app.debug = args.debug
    lock.publish(url=app.url, token=app.token, mode=mode)

    stopping = threading.Event()

    def stop(_signum: int | None = None, _frame: FrameType | None = None) -> None:
        if not stopping.is_set():
            stopping.set()
            app.shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with contextlib.suppress(AttributeError):
        signal.signal(signal.SIGHUP, stop)

    try:
        if mode == "window":
            from netpulse import window

            server_thread = threading.Thread(target=app.serve_forever, daemon=True)
            server_thread.start()
            code = window.run(app)
            stop()
            server_thread.join(5)
            return code
        print(f"NetPulse {__version__} is running at {app.url}")
        print(f"Open this link (it contains the access token): {app.launch_url}")
        print("Press Ctrl+C to stop.")
        sys.stdout.flush()
        if mode == "browser":
            if not open_browser(app.launch_url):
                print("netpulse: could not start a web browser (xdg-open missing)")
            start_idle_watch(app, BROWSER_IDLE_TIMEOUT_S, stop)
        app.serve_forever()
        return 0
    finally:
        app.close()
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
