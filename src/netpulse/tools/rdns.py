# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Reverse DNS (PTR) lookup with ``dig -x``."""

from __future__ import annotations

from netpulse import validators as v
from netpulse.tools import dig
from netpulse.tools import dnscommon as dc
from netpulse.tools.base import Params, Summary, Tool, command_runner


def validate(params: Params) -> Params:
    resolver = v.choice(params.get("resolver"), dc.RESOLVERS, "resolver", default="system")
    return {
        "address": str(v.ip_address(params.get("address"), "address")),
        "resolver": resolver,
        "custom": v.host_or_ip(params.get("custom"), "custom") if resolver == "custom" else "",
    }


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    argv = ["dig", "-r", "+yaml", f"+timeout={dig.TIMEOUT_S}", f"+tries={dig.TRIES}"]
    server = dig.server_of(p)
    if server:
        argv.append(f"@{server}")
    # -x takes the address as its own argument, so it cannot be read as an option.
    return [*argv, "-x", p["address"]]


def timeout(params: Params) -> float:
    return dig.TIMEOUT_S * dig.TRIES * 3 + 10


def parse(output: str) -> Summary:
    summary = dig.parse(output)
    ptr = [r["data"] for r in summary.get("answer", []) if r.get("type") == "PTR"]
    summary["names"] = ptr
    question = summary.get("question") or []
    summary["reverse_name"] = question[0]["name"] if question else None
    if summary.get("status") == "ok":
        summary["message"] = f"{len(ptr)} name{'s' if len(ptr) != 1 else ''}: {', '.join(ptr)}"
    elif summary.get("rcode") == "NXDOMAIN":
        summary["message"] = "no PTR record: this address has no reverse DNS name"
    return summary


TOOL = Tool(
    name="rdns",
    title="Reverse DNS",
    group="DNS",
    description="Find the host name for an IP address (PTR lookup).",
    validate=validate,
    run=command_runner(build_argv, parse, timeout),
    timeout=timeout,
    binaries=("dig",),
    target=lambda p: p["address"],
)
