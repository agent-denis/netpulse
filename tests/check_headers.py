# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Check that every source file starts with the SPDX + copyright header.

Run directly (``python3 tests/check_headers.py``) or through pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Extensions / names that count as "source files".
CHECKED_SUFFIXES = {
    ".py",
    ".js",
    ".css",
    ".html",
    ".svg",
    ".xml",
    ".desktop",
    ".spec",
    ".toml",
    ".yml",
    ".yaml",
    ".1",
    ".sh",
    ".rpmlintrc",
}
CHECKED_NAMES = {"Makefile"}
SKIP_DIRS = {".git", "build", "dist", "fixtures", "__pycache__", ".pytest_cache", ".ruff_cache"}
# Files whose format cannot carry a comment header.
SKIP_FILES = {"LICENSE"}

SPDX = "SPDX-License-Identifier: GPL-3.0-or-later"
COPYRIGHT = "Copyright (C) "
HEAD_LINES = 6  # header must appear within the first lines (after shebang / xml decl)


def source_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(p in SKIP_DIRS for p in path.relative_to(ROOT).parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.suffix in CHECKED_SUFFIXES or path.name in CHECKED_NAMES:
            files.append(path)
    return sorted(files)


def missing_header(path: Path) -> bool:
    head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:HEAD_LINES]
    text = "\n".join(head)
    return SPDX not in text or COPYRIGHT not in text


def main() -> int:
    bad = [p.relative_to(ROOT) for p in source_files() if missing_header(p)]
    for p in bad:
        print(f"missing SPDX/copyright header: {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
