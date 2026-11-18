# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Common interface for tool modules.

A tool module exposes:

* ``validate(params) -> dict``: normalise and check user input (idempotent)
* ``build_argv(params) -> list[str]``: validate, then build the command line
* ``parse(output) -> dict``: turn captured output into a summary
* ``TOOL``: a :class:`Tool` describing it for the registry/UI
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from netpulse.jobs import JobContext, JobFunc

Params = dict[str, Any]
Summary = dict[str, Any]

GROUPS = ("Connectivity", "DNS", "Web & TLS", "Local", "Utilities")


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    group: str
    description: str
    validate: Callable[[Params], Params]
    run: JobFunc
    timeout: Callable[[Params], float]
    binaries: tuple[str, ...] = ()  # any one of these is enough
    target: Callable[[Params], str] = field(default=lambda p: str(p.get("host", "")))
    notes: tuple[str, ...] = ()

    def info(self, available: bool, missing_hint: str) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "group": self.group,
            "description": self.description,
            "binaries": list(self.binaries),
            "available": available,
            "install_hint": missing_hint,
            "notes": list(self.notes),
        }


def command_runner(
    build_argv: Callable[[Params], list[str]],
    parse: Callable[[str], Summary],
    timeout: Callable[[Params], float],
    *,
    live: Callable[[str], Summary | None] | None = None,
    live_every: int = 1,
) -> JobFunc:
    """A JobFunc for the common case: run one command, parse its output.

    *live*, if given, is called with the output so far after each line and may
    return a partial summary to publish (e.g. the ping chart).
    """

    def run(ctx: JobContext, params: Params) -> Summary:
        argv = build_argv(params)
        buf: list[str] = []
        count = 0

        def on_line(line: str) -> None:
            nonlocal count
            buf.append(line)
            count += 1
            if live is not None and count % live_every == 0:
                partial = live("".join(buf))
                if partial is not None:
                    ctx.summary(partial)

        result = ctx.run(argv, timeout=timeout(params), on_line=on_line)
        summary = parse(result.output)
        summary["exit_code"] = result.returncode
        if result.timed_out:
            summary["status"] = "error"
            summary["message"] = "the command timed out"
        elif result.cancelled:
            summary.setdefault("message", "cancelled")
        return summary

    return run


def status_from(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "error"
    return "warning" if warn else "ok"
