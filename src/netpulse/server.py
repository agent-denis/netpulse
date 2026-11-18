# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Local HTTP server: static UI, JSON API and Server-Sent Events.

Every request is checked for an allowed ``Host`` header (DNS rebinding) and,
if present, a matching ``Origin``. Every ``/api/*`` request also needs the
per-launch token.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from netpulse import APP_ID, __version__, detect, security
from netpulse import validators as v
from netpulse.config import Settings
from netpulse.history import History
from netpulse.jobs import Job, JobLimitError, JobManager
from netpulse.tools import base
from netpulse.tools.base import Tool

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY = 64 * 1024
SSE_KEEPALIVE_S = 5.0

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json",
    ".ico": "image/x-icon",
}

_JOB_RE = re.compile(r"^/api/jobs/([0-9a-f]{16})(/events)?$")
_HISTORY_RE = re.compile(r"^/api/history/([0-9a-f]{16})$")


class App:
    """Shared state for all request handlers."""

    def __init__(
        self,
        tools: dict[str, Tool],
        *,
        bind: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
        settings: Settings | None = None,
        history: History | None = None,
        static_dir: Path = STATIC_DIR,
        manager: JobManager | None = None,
    ) -> None:
        if not security.is_loopback(bind):
            raise ValueError(f"refusing to listen on non-loopback address {bind!r}")
        self.tools = tools
        self.bind = bind
        self.token = token or security.new_token()
        self.settings = settings or Settings()
        self.history = history or History(max_entries=self.settings.get()["history_max"])
        self.static_dir = static_dir
        self.manager = manager or JobManager(on_finish=self._save_history)
        if self.manager.on_finish is None:
            self.manager.on_finish = self._save_history
        self.on_present: Callable[[], None] | None = None
        self.last_activity = time.monotonic()
        self.seen_client = False
        self.debug = False
        self.httpd = _Server((bind, port), Handler)
        self.httpd.app = self
        self.port: int = self.httpd.server_address[1]

    # ---------------------------------------------------------------- helpers
    @property
    def url(self) -> str:
        host = f"[{self.bind}]" if ":" in self.bind else self.bind
        return f"http://{host}:{self.port}/"

    @property
    def launch_url(self) -> str:
        return f"{self.url}#token={self.token}"

    def _save_history(self, job: Job) -> None:
        if self.settings.get().get("history_enabled", True):
            self.history.append(job.record())

    def tool_infos(self) -> list[dict[str, Any]]:
        found = detect.detect()
        infos = []
        for tool in self.tools.values():
            available = not tool.binaries or any(
                found.get(b) or detect.which(b) for b in tool.binaries
            )
            infos.append(
                tool.info(available, "" if available else detect.install_hint(tool.binaries))
            )
        return infos

    def serve_forever(self) -> None:
        self.httpd.serve_forever(poll_interval=0.25)

    def shutdown(self) -> None:
        self.manager.shutdown()
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()

    def close(self) -> None:
        self.manager.shutdown()
        self.httpd.server_close()


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    app: App


class HTTPError(Exception):
    def __init__(self, status: HTTPStatus, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.field = field


class Handler(BaseHTTPRequestHandler):
    server: _Server
    server_version = f"NetPulse/{__version__}"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> App:
        return self.server.app

    # ---------------------------------------------------------------- plumbing
    def log_message(self, format: str, *args: Any) -> None:
        if self.app.debug:
            msg = format % args
            msg = re.sub(r"token=[^&\s\"]+", "token=REDACTED", msg)
            sys.stderr.write(f"netpulse: {self.address_string()} {msg}\n")

    def _send_headers(self, status: int, ctype: str, length: int | None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        for key, value in security.SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()

    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self._send_headers(status, "application/json", len(body))
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str, field: str | None = None) -> None:
        # The request body may be unread (e.g. 413/415): never reuse this connection.
        self.close_connection = True
        payload: dict[str, Any] = {"error": message}
        if field:
            payload["field"] = field
        self._json(payload, status)

    def _read_json(self) -> Any:
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise HTTPError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json"
            )
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "bad Content-Length") from None
        if length < 0 or length > MAX_BODY:
            raise HTTPError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "invalid JSON") from None

    def _guard(self, path: str, query: dict[str, list[str]]) -> bool:
        """Host/Origin checks for everything, token for the API."""
        app = self.app
        if not security.check_host(self.headers.get("Host"), app.bind, app.port):
            self._error(HTTPStatus.FORBIDDEN, "invalid Host header")
            return False
        if not security.check_origin(self.headers.get("Origin"), app.bind, app.port):
            self._error(HTTPStatus.FORBIDDEN, "cross-origin request refused")
            return False
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site and fetch_site not in ("same-origin", "none"):
            self._error(HTTPStatus.FORBIDDEN, "cross-site request refused")
            return False
        if path.startswith("/api/"):
            supplied = self.headers.get(security.TOKEN_HEADER)
            if supplied is None and path.endswith("/events"):
                supplied = (query.get("token") or [None])[0]
            if not security.check_token(app.token, supplied):
                self._error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                return False
            app.last_activity = time.monotonic()
            app.seen_client = True
        return True

    def _dispatch(self, method: str) -> None:
        parts = urlsplit(self.path)
        path, query = parts.path, parse_qs(parts.query)
        if not self._guard(path, query):
            return
        try:
            if path.startswith("/api/"):
                self._api(method, path, query)
            elif method in ("GET", "HEAD"):
                self._static(path, head=method == "HEAD")
            else:
                raise HTTPError(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        except HTTPError as exc:
            self._error(exc.status, exc.message, exc.field)
        except v.ValidationError as exc:
            self._error(HTTPStatus.BAD_REQUEST, exc.message, exc.field)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    # ---------------------------------------------------------------- static
    def _static(self, path: str, head: bool = False) -> None:
        if path in ("", "/"):
            path = "/index.html"
        root = self.app.static_dir.resolve()
        try:
            target = (root / path.lstrip("/")).resolve()
        except (OSError, ValueError):
            raise HTTPError(HTTPStatus.NOT_FOUND, "not found") from None
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPError(HTTPStatus.NOT_FOUND, "not found")
        ctype = MIME.get(target.suffix)
        if ctype is None:
            raise HTTPError(HTTPStatus.NOT_FOUND, "not found")
        body = target.read_bytes()
        if target.name == "index.html":
            # Bake the saved theme into <html> so the first paint is already right.
            theme = self.app.settings.get().get("theme", "system")
            if theme in ("system", "light", "dark"):
                body = body.replace(
                    b'data-theme-pref="system"', f'data-theme-pref="{theme}"'.encode(), 1
                )
        self._send_headers(200, ctype, len(body))
        if not head:
            self.wfile.write(body)

    # ---------------------------------------------------------------- API
    def _api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        app = self.app
        route = (method, path)
        if route == ("GET", "/api/info"):
            self._json(
                {
                    "name": "NetPulse",
                    "version": __version__,
                    "app_id": APP_ID,
                    "groups": list(base.GROUPS),
                    "tools": app.tool_infos(),
                    "settings": app.settings.get(),
                    "history_path": str(app.history.path),
                    "settings_path": str(app.settings.path),
                }
            )
        elif route == ("GET", "/api/ping"):
            self._json({"ok": True})
        elif route == ("POST", "/api/present"):
            if app.on_present is not None:
                app.on_present()
            self._json({"ok": True, "window": app.on_present is not None})
        elif route == ("GET", "/api/settings"):
            self._json(app.settings.get())
        elif route == ("PUT", "/api/settings"):
            body = self._read_json()
            if not isinstance(body, dict):
                raise HTTPError(HTTPStatus.BAD_REQUEST, "expected an object")
            updated = app.settings.update(body)
            app.history.set_max(updated["history_max"])
            self._json(updated)
        elif route == ("GET", "/api/history"):
            q = (query.get("q") or [""])[0][:200]
            tool = (query.get("tool") or [""])[0][:40]
            limit = v.int_range((query.get("limit") or [None])[0], 1, 1000, "limit", default=200)
            self._json({"entries": app.history.list(q, limit, tool)})
        elif route == ("DELETE", "/api/history"):
            app.history.clear()
            self._json({"ok": True})
        elif method == "GET" and (m := _HISTORY_RE.match(path)):
            entry = app.history.get(m.group(1))
            if entry is None:
                raise HTTPError(HTTPStatus.NOT_FOUND, "history entry not found")
            self._json(entry)
        elif route == ("GET", "/api/jobs"):
            self._json({"jobs": [j.snapshot() for j in app.manager.list()]})
        elif route == ("POST", "/api/jobs"):
            self._create_job()
        elif m := _JOB_RE.match(path):
            job = app.manager.get(m.group(1))
            if job is None:
                raise HTTPError(HTTPStatus.NOT_FOUND, "job not found")
            if method == "GET" and m.group(2):
                self._sse(job)
            elif method == "GET":
                self._json({**job.snapshot(), "output": job.output})
            elif method == "DELETE":
                app.manager.cancel(job.id)
                self._json({"ok": True})
            else:
                raise HTTPError(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        else:
            raise HTTPError(HTTPStatus.NOT_FOUND, "unknown API endpoint")

    def _create_job(self) -> None:
        app = self.app
        body = self._read_json()
        if not isinstance(body, dict):
            raise HTTPError(HTTPStatus.BAD_REQUEST, "expected an object")
        name = body.get("tool")
        tool = app.tools.get(name) if isinstance(name, str) else None
        if tool is None:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "unknown tool", "tool")
        raw = body.get("params") or {}
        if not isinstance(raw, dict):
            raise HTTPError(HTTPStatus.BAD_REQUEST, "params must be an object", "params")
        params = tool.validate(raw)
        title = f"{tool.title}: {tool.target(params)}".rstrip(": ")
        try:
            job = app.manager.submit(tool.name, title, params, tool.run, tool.timeout(params))
        except JobLimitError as exc:
            raise HTTPError(HTTPStatus.TOO_MANY_REQUESTS, str(exc)) from None
        self._json(job.snapshot(), HTTPStatus.CREATED)

    def _sse(self, job: Job) -> None:
        app = self.app
        try:
            seq = int(self.headers.get("Last-Event-ID", "-1")) + 1
        except ValueError:
            seq = 0
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        for key, value in security.SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        app.manager.subscribe(job)
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                events = job.events_since(seq, SSE_KEEPALIVE_S)
                if not events:
                    if app.manager.closing:
                        break
                    if job.finished:
                        time.sleep(0.05)
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                chunks = []
                done = False
                for event in events:
                    data = json.dumps(event, separators=(",", ":"))
                    chunks.append(f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n")
                    done = done or event["type"] == "end"
                seq = events[-1]["seq"] + 1
                self.wfile.write("".join(chunks).encode())
                self.wfile.flush()
                if done:
                    break
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            app.manager.unsubscribe(job)


def start_idle_watch(
    app: App, idle_timeout: float, on_idle: Callable[[], None], interval: float = 5.0
) -> None:
    """Stop the server when the page has been gone for a while (browser mode)."""

    def loop() -> None:
        while not app.manager.closing:
            time.sleep(interval)
            idle = time.monotonic() - app.last_activity
            if app.seen_client and idle > idle_timeout and not app.manager.running():
                on_idle()
                return

    with contextlib.suppress(RuntimeError):
        threading.Thread(target=loop, name="idle-watch", daemon=True).start()
