# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""nslookup (bind-utils)."""

from __future__ import annotations

import re
from typing import Any

from netpulse import validators as v
from netpulse.tools import dnscommon as dc
from netpulse.tools.base import Params, Summary, Tool, command_runner

TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "CAA", "PTR", "ANY")
TIMEOUT_S = 5
RETRY = 2

# "<owner>\t<description> = <data>"
_RECORD_RE = re.compile(r"^(\S+)\s+([a-zA-Z][\w ]*?) = (.*)$")
_DESCRIPTIONS = {
    "mail exchanger": "MX",
    "nameserver": "NS",
    "text": "TXT",
    "canonical name": "CNAME",
    "name": "PTR",
    "service": "SRV",
    "internet address": "A",
    "has AAAA address": "AAAA",
    "AAAA address": "AAAA",
    "rdata_257": "CAA",
}
_SOA_FIELDS = ("origin", "mail addr", "serial", "refresh", "retry", "expire", "minimum")


def validate(params: Params) -> Params:
    rtype = v.choice(params.get("type"), TYPES, "type", default="A")
    name = v.safe_text(params.get("name"), "name", max_len=254)
    name = v.host_or_ip(name, "name") if v.is_ip(name) else v.hostname(name, "name", dns_name=True)
    resolver = v.choice(params.get("resolver"), dc.RESOLVERS, "resolver", default="system")
    custom = v.host_or_ip(params.get("custom"), "custom") if resolver == "custom" else ""
    return {"name": name, "type": rtype, "resolver": resolver, "custom": custom}


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    # nslookup has no "--"; the name and server are validated and never start with "-".
    argv = ["nslookup", f"-type={p['type']}", f"-timeout={TIMEOUT_S}", f"-retry={RETRY}", p["name"]]
    if p["resolver"] == "custom":
        argv.append(p["custom"])
    elif p["resolver"] != "system":
        argv.append(p["resolver"])
    return argv


def timeout(params: Params) -> float:
    return TIMEOUT_S * (RETRY + 1) * 2 + 10


def parse(output: str) -> Summary:
    server = None
    authoritative = True
    answer: list[dict[str, Any]] = []
    authority: list[dict[str, Any]] = []
    target = answer
    errors: list[str] = []
    rcode = None
    pending_name: str | None = None
    soa: dict[str, Any] | None = None
    for raw in output.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Server:"):
            server = stripped.split(None, 1)[1] if " " in stripped or "\t" in stripped else None
            continue
        if stripped.startswith("Address:") and pending_name is None:
            if server and "#" in stripped:
                server = stripped.split(None, 1)[1]
            continue
        if stripped == "Non-authoritative answer:":
            authoritative = False
            continue
        if stripped.startswith("Authoritative answers can be found from"):
            target = authority
            continue
        if m := re.match(r"^\*\* server can't find (\S+?): (\w+)", stripped):
            rcode = m.group(2)
            continue
        if m := re.match(r"^\*\*\* Can't find (\S+?): (.*)$", stripped):
            rcode = rcode or "NOERROR"
            errors.append(stripped.strip("* "))
            continue
        if stripped.startswith(";;"):
            msg = stripped.lstrip("; ").strip()
            if "SERVFAIL" in msg:
                rcode = "SERVFAIL"
            else:
                errors.append(msg)
            continue
        if stripped.startswith("Name:"):
            pending_name = stripped.split(None, 1)[1]
            continue
        if stripped.startswith("Address:") and pending_name is not None:
            addr = stripped.split(None, 1)[1]
            rtype = "AAAA" if ":" in addr else "A"
            target.append({"name": pending_name, "type": rtype, "data": addr})
            pending_name = None
            continue
        if raw.startswith(("\t", " ")) and soa is not None:
            key, _, value = stripped.partition(" = ")
            if key in _SOA_FIELDS:
                soa[key] = int(value) if value.isdigit() else value
                if key == "minimum":
                    target.append(
                        {"name": soa.pop("_name"), "type": "SOA", "data": " ".join(
                            str(soa[k]) for k in _SOA_FIELDS if k in soa
                        ), "soa": dict(soa)}
                    )  # fmt: skip
                    soa = None
            continue
        if m := _RECORD_RE.match(stripped):
            desc = m.group(2)
            target.append(
                {"name": m.group(1), "type": _DESCRIPTIONS.get(desc, desc), "data": m.group(3)}
            )
            continue
        if re.fullmatch(r"\S+", stripped) and not stripped.startswith(("*", ";")):
            soa = {"_name": stripped}  # an SOA block starts with the bare owner name
            continue

    if rcode is None and (answer or authority):
        rcode = "NOERROR"
    summary: Summary = {
        "server": server,
        "authoritative": authoritative,
        "rcode": rcode,
        "answer": answer,
        "authority": authority,
        "answer_count": len(answer),
        "errors": errors,
    }
    if rcode in dc.ERROR_RCODES:
        summary["status"], summary["message"] = "error", rcode
    elif rcode in dc.NEGATIVE_RCODES:
        summary["status"], summary["message"] = "warning", f"{rcode}: the name does not exist"
    elif errors and not answer:
        summary["status"], summary["message"] = "error", "; ".join(errors)
    elif not answer:
        summary["status"], summary["message"] = "warning", "no records of this type"
    else:
        summary["status"] = "ok"
        n = len(answer)
        summary["message"] = f"{n} record{'s' if n != 1 else ''}"
    return summary


TOOL = Tool(
    name="nslookup",
    title="nslookup",
    group="DNS",
    description="Simple DNS lookup of a name or address.",
    validate=validate,
    run=command_runner(build_argv, parse, timeout),
    timeout=timeout,
    binaries=("nslookup",),
    target=lambda p: f"{p['name']} {p['type']}",
)
