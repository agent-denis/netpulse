# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Native GTK 4 + WebKitGTK 6.0 window (optional, via PyGObject)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from netpulse.server import App


def available() -> bool:
    """Native window support lands in a later phase."""
    return False


def run(app: App) -> int:  # pragma: no cover - replaced in phase 5
    raise NotImplementedError
