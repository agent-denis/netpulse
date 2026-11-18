# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Command-line entry point (``netpulse``)."""

from __future__ import annotations

import sys

from netpulse import __version__


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--version" in args:
        print(f"netpulse {__version__}")
        return 0
    print("NetPulse is not implemented yet.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
