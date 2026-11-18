# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Tool registry."""

from __future__ import annotations

import importlib

from netpulse.tools.base import Tool

# Order = order in the sidebar (within each group).
MODULES: tuple[str, ...] = ()

REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    REGISTRY[tool.name] = tool
    return tool


def load_all() -> dict[str, Tool]:
    for mod in MODULES:
        module = importlib.import_module(f"netpulse.tools.{mod}")
        register(module.TOOL)
    return REGISTRY
