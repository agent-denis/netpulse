# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""host (bind-utils): quick lookups."""

from __future__ import annotations

import re
from typing import Any

from netpulse import validators as v
from netpulse.tools import dnscommon as dc
from netpulse.tools.base import Params, Summary, Tool, command_runner

TYPES = ("default", "A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "CAA", "PTR", "ANY")
WAIT_S = 5

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(\S+) has address (\S+)$"), "A"),
    (re.compile(r"^(\S+) has IPv6 address (\S+)$"), "AAAA"),
    (re.compile(r"^(\S+) mail is handled by (.+)$"), "MX"),
    (re.compile(r"^(\S+) is an alias for (\S+)$"), "CNAME"),
    (re.compile(r"^(\S+) domain name pointer (\S+)$"), "PTR"),
    (re.compile(r"^(\S+) name server (\S+)$"), "NS"),
    (re.compile(r"^(\S+) descriptive text (.+)$"), "TXT"),
    (re.compile(r"^(\S+) has (\w+) record (.+)$"), "*"),
)
_NOTFOUND_RE = re.compile(r"^Host (\S+) not found: \d+\((\w+)\)")
_NORECORD_RE = re.compile(r"^(\S+) has no (\w+) record")


def validate(params: Params) -> Params:
    rtype = v.choice(params.get("type"), TYPES, "type", default="default")
    name = v.safe_text(params.get("name"), "name", max_len=254)
    name = v.host_or_ip(name, "name") if v.is_ip(name) else v.hostname(name, "name", dns_name=True)
    resolver = v.choice(params.get("resolver"), dc.RESOLVERS, "resolver", default="system")
    custom = v.host_or_ip(params.get("custom"), "custom") if resolver == "custom" else ""
    return {"name": name, "type": rtype, "resolver": resolver, "custom": custom}


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    argv = ["host", "-W", str(WAIT_S)]
    if p["type"] != "default":
        argv += ["-t", p["type"]]
    argv += ["--", p["name"]]
    if p["resolver"] == "custom":
        argv.append(p["custom"])
    elif p["resolver"] != "system":
        argv.append(p["resolver"])
    return argv


def timeout(params: Params) -> float:
    return WAIT_S * 6 + 10


def parse(output: str) -> Summary:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    rcode = None
    server = None
    missing: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("$ "):
            continue
        if line.startswith("Address:") and server is None:
            server = line.split(None, 1)[1]
            continue
        if line.startswith(("Using domain server", "Name:", "Aliases:")):
            continue
        if m := _NOTFOUND_RE.match(line):
            rcode = m.group(2)
            continue
        if m := _NORECORD_RE.match(line):
            missing.append(m.group(2))
            continue
        if line.startswith(";;"):
            msg = line.lstrip("; ").strip()
            if msg not in errors:
                errors.append(msg)
            continue
        for pattern, rtype in _PATTERNS:
            if m := pattern.match(line):
                if rtype == "*":
                    records.append({"name": m.group(1), "type": m.group(2), "data": m.group(3)})
                else:
                    records.append({"name": m.group(1), "type": rtype, "data": m.group(2)})
                break
    if rcode is None and records:
        rcode = "NOERROR"
    summary: Summary = {
        "records": records,
        "answer_count": len(records),
        "rcode": rcode,
        "server": server,
        "missing": missing,
        "errors": errors,
    }
    if rcode in dc.ERROR_RCODES:
        summary["status"], summary["message"] = "error", rcode
    elif rcode in dc.NEGATIVE_RCODES:
        summary["status"], summary["message"] = "warning", f"{rcode}: the name does not exist"
    elif errors and not records:
        summary["status"], summary["message"] = "error", "; ".join(errors)
    elif not records:
        summary["status"], summary["message"] = "warning", "no records found"
    else:
        n = len(records)
        summary["status"], summary["message"] = "ok", f"{n} record{'s' if n != 1 else ''}"
    return summary


TOOL = Tool(
    name="host",
    title="host",
    group="DNS",
    description="Quick DNS lookup: addresses, mail servers and aliases in plain sentences.",
    validate=validate,
    run=command_runner(build_argv, parse, timeout),
    timeout=timeout,
    binaries=("host",),
    target=lambda p: p["name"] if p["type"] == "default" else f"{p['name']} {p['type']}",
)
