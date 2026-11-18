# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""ping (iputils)."""

from __future__ import annotations

import re
from typing import Any

from netpulse import validators as v
from netpulse.tools.base import Params, Summary, Tool, command_runner

FAMILIES = ("auto", "4", "6")
REPLY_WAIT_S = 2

_HEADER_RE = re.compile(r"^PING (\S+) \(([^)]+)\)")
_REPLY_RE = re.compile(
    r"^(\d+) bytes from (.+?): icmp_seq=(\d+)(?: ttl=(\d+))?(?: time=([\d.]+) ms)?"
    r"(?P<dup> \(DUP!\))?"
)
_NOANSWER_RE = re.compile(r"^no answer yet for icmp_seq=(\d+)")
_ICMP_ERR_RE = re.compile(r"^From (\S+?)(?: \([^)]*\))? icmp_seq=(\d+) (.+)$")
_STATS_RE = re.compile(
    r"^(\d+) packets transmitted, (\d+) received(?:, \+(\d+) duplicates)?"
    r"(?:, \+(\d+) errors)?, ([\d.]+)% packet loss"
)
_RTT_RE = re.compile(r"^rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms")


def validate(params: Params) -> Params:
    return {
        "host": v.host_or_ip(params.get("host"), "host", allow_scope=True),
        "count": v.int_range(params.get("count"), 1, 100, "count", default=4),
        "interval": v.float_range(params.get("interval"), 0.2, 60.0, "interval", default=1.0),
        "size": v.int_range(params.get("size"), 0, 65507, "size", default=56),
        "family": v.choice(params.get("family"), FAMILIES, "family", default="auto"),
    }


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    argv = ["ping", "-n", "-O", "-c", str(p["count"]), "-i", f"{p['interval']:g}"]
    argv += ["-s", str(p["size"]), "-W", str(REPLY_WAIT_S)]
    if p["family"] != "auto":
        argv.append(f"-{p['family']}")
    return [*argv, "--", p["host"]]


def timeout(params: Params) -> float:
    return params["count"] * params["interval"] + REPLY_WAIT_S + 15


def parse(output: str) -> Summary:
    target = address = None
    replies: dict[int, dict[str, Any]] = {}
    pending: set[int] = set()
    icmp_errors: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    errors: list[str] = []
    duplicates = 0
    for raw in output.splitlines():
        line = raw.strip()
        if m := _HEADER_RE.match(line):
            target, address = m.group(1), m.group(2)
        elif m := _REPLY_RE.match(line):
            seq = int(m.group(3))
            if m.group("dup"):
                duplicates += 1
                continue
            replies[seq] = {
                "seq": seq,
                "rtt": float(m.group(5)) if m.group(5) else None,
                "ttl": int(m.group(4)) if m.group(4) else None,
                "bytes": int(m.group(1)),
                "from": m.group(2),
            }
            pending.discard(seq)
        elif m := _NOANSWER_RE.match(line):
            pending.add(int(m.group(1)))
        elif m := _ICMP_ERR_RE.match(line):
            seq = int(m.group(2))
            icmp_errors.append({"from": m.group(1), "seq": seq, "message": m.group(3)})
            pending.add(seq)
        elif m := _STATS_RE.match(line):
            stats.update(
                transmitted=int(m.group(1)),
                received=int(m.group(2)),
                loss_pct=float(m.group(5)),
            )
            if m.group(3):
                duplicates = int(m.group(3))
            if m.group(4):
                stats["errors"] = int(m.group(4))
        elif m := _RTT_RE.match(line):
            stats.update(
                min=float(m.group(1)),
                avg=float(m.group(2)),
                max=float(m.group(3)),
                mdev=float(m.group(4)),
            )
        elif line.startswith("ping: "):
            errors.append(line[len("ping: ") :])

    lost = set(pending)
    if "transmitted" in stats:
        lost |= {s for s in range(1, stats["transmitted"] + 1) if s not in replies}
    lost -= set(replies)
    points = sorted(
        [*replies.values(), *({"seq": s, "rtt": None, "ttl": None} for s in lost)],
        key=lambda p: p["seq"],
    )
    rtts = [p["rtt"] for p in replies.values() if p["rtt"] is not None]
    summary: Summary = {
        "target": target,
        "address": address,
        "transmitted": stats.get("transmitted", len(points)),
        "received": stats.get("received", len(replies)),
        "loss_pct": stats.get("loss_pct"),
        "duplicates": duplicates,
        "errors": stats.get("errors", 0),
        "min": stats.get("min", min(rtts) if rtts else None),
        "avg": stats.get("avg", round(sum(rtts) / len(rtts), 3) if rtts else None),
        "max": stats.get("max", max(rtts) if rtts else None),
        "mdev": stats.get("mdev"),
        "points": points,
        "icmp_errors": icmp_errors,
        "complete": "transmitted" in stats,
    }
    if summary["loss_pct"] is None and summary["transmitted"]:
        summary["loss_pct"] = round(100 * (1 - summary["received"] / summary["transmitted"]), 1)
    if errors:
        summary["status"], summary["message"] = "error", "; ".join(errors)
    elif summary["complete"] and summary["received"] == 0:
        summary["status"], summary["message"] = "error", "no replies received (100% packet loss)"
    elif summary["loss_pct"]:
        summary["status"] = "warning"
        summary["message"] = f"{round(summary['loss_pct'], 1):g}% packet loss"
    else:
        summary["status"] = "ok"
        if summary["complete"]:
            n = summary["received"]
            summary["message"] = "1 reply received" if n == 1 else f"all {n} replies received"
    return summary


TOOL = Tool(
    name="ping",
    title="Ping",
    group="Connectivity",
    description="Send ICMP echo requests and measure round-trip time and packet loss.",
    validate=validate,
    run=command_runner(build_argv, parse, timeout, live=parse),
    timeout=timeout,
    binaries=("ping",),
)
