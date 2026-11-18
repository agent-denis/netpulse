# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""Access control for the local HTTP server: token, Host and Origin checks."""

from __future__ import annotations

import hmac
import ipaddress
import secrets

TOKEN_HEADER = "X-NetPulse-Token"  # noqa: S105 (a header name)

# Content-Security-Policy: no inline script/style, nothing from other origins.
CSP = "; ".join(
    [
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "manifest-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
}


def new_token() -> str:
    return secrets.token_urlsafe(32)


def check_token(expected: str, supplied: str | None) -> bool:
    """Constant-time token comparison. Empty/missing tokens never match."""
    if not expected or not supplied:
        return False
    return hmac.compare_digest(expected.encode(), supplied.encode())


def is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def allowed_hosts(bind: str, port: int) -> set[str]:
    """Host header values we accept (anything else may be DNS rebinding)."""
    hosts = {f"localhost:{port}"}
    if ":" in bind:
        hosts.add(f"[{bind}]:{port}")
    else:
        hosts.add(f"{bind}:{port}")
    hosts.add(f"127.0.0.1:{port}")
    return hosts


def check_host(host_header: str | None, bind: str, port: int) -> bool:
    if not host_header:
        return False
    return host_header.strip().lower() in allowed_hosts(bind, port)


def check_origin(origin: str | None, bind: str, port: int) -> bool:
    """A missing Origin is fine (same-origin GET/navigation). A present one must be ours."""
    if origin is None:
        return True
    origin = origin.strip().lower()
    if origin == "null":
        return False
    return origin in {f"http://{h}" for h in allowed_hosts(bind, port)}
