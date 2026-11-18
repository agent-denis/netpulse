# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis

import os
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
FIXTURES = TESTS / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("NETPULSE_NETWORK_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="network test (set NETPULSE_NETWORK_TESTS=1)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
