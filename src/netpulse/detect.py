# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""Detect which external tools are installed."""

from __future__ import annotations

import shutil

from netpulse.jobs import SAFE_PATH

# binary → Fedora package that provides it
PACKAGES: dict[str, str] = {
    "ping": "iputils",
    "tracepath": "iputils",
    "traceroute": "traceroute",
    "mtr": "mtr",
    "dig": "bind-utils",
    "nslookup": "bind-utils",
    "host": "bind-utils",
    "whois": "whois",
    "curl": "curl",
    "openssl": "openssl",
    "ip": "iproute",
    "ss": "iproute",
    "resolvectl": "systemd-resolved",
}


def which(binary: str) -> str | None:
    return shutil.which(binary, path=SAFE_PATH)


def detect() -> dict[str, str | None]:
    return {binary: which(binary) for binary in PACKAGES}


def install_hint(binaries: tuple[str, ...] | list[str]) -> str:
    pkgs = sorted({PACKAGES.get(b, b) for b in binaries})
    return f"sudo dnf install {' '.join(pkgs)}" if pkgs else ""
