# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""Shared DNS helpers: record types, resolver presets, ``dig`` output parsing."""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Any

from netpulse import miniyaml
from netpulse import validators as v

RECORD_TYPES = (
    "A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "CAA", "PTR", "DNSKEY", "DS", "ANY",
)  # fmt: skip
RESOLVERS = ("system", "1.1.1.1", "8.8.8.8", "9.9.9.9", "custom")
RESOLVER_LABELS = {
    "1.1.1.1": "Cloudflare (1.1.1.1)",
    "8.8.8.8": "Google (8.8.8.8)",
    "9.9.9.9": "Quad9 (9.9.9.9)",
}

ERROR_RCODES = {"SERVFAIL", "REFUSED", "FORMERR", "NOTIMP", "BADVERS", "NOTAUTH", "NOTZONE"}
NEGATIVE_RCODES = {"NXDOMAIN", "YXDOMAIN", "NXRRSET", "YXRRSET"}


def dns_name_or_ip(value: Any, rtype: str, field: str = "name") -> str:
    """A DNS name. For PTR an IP literal is accepted and turned into its reverse name."""
    text = v.safe_text(value, field, max_len=254)
    if rtype == "PTR" and v.is_ip(text):
        return ipaddress.ip_address(v.host_or_ip(text, field)).reverse_pointer + "."
    return v.hostname(text, field, dns_name=True)


def parse_record(text: str) -> dict[str, Any]:
    """'name. 300 IN A 1.2.3.4' → dict. Question lines have no TTL."""
    parts = text.split(None, 4)
    if len(parts) >= 4 and parts[1].isdigit():
        name, ttl, klass, rtype = parts[:4]
        data = parts[4] if len(parts) == 5 else ""
        return {"name": name, "ttl": int(ttl), "class": klass, "type": rtype, "data": data}
    if len(parts) >= 3:
        return {"name": parts[0], "class": parts[1], "type": parts[2], "data": " ".join(parts[3:])}
    return {"name": text, "ttl": None, "class": "", "type": "", "data": ""}


def _ms_between(a: Any, b: Any) -> float | None:
    try:
        t0 = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((t1 - t0).total_seconds() * 1000, 1)


def _message_summary(msg: dict[str, Any]) -> dict[str, Any]:
    data = msg.get("response_message_data") or {}
    opt = data.get("OPT_PSEUDOSECTION") or {}
    edns = opt.get("EDNS") or {}
    ede = edns.get("EDE") if isinstance(edns, dict) else None
    ede_text = None
    if isinstance(ede, dict):
        ede_text = str(ede.get("INFO-CODE", ""))
        if ede.get("EXTRA-TEXT"):
            ede_text += f": {ede['EXTRA-TEXT']}"

    def section(name: str) -> list[dict[str, Any]]:
        return [parse_record(str(r)) for r in (data.get(name) or []) if r]

    server = msg.get("response_address")
    port = msg.get("response_port")
    return {
        "kind": msg.get("type"),
        "status": data.get("status"),
        "opcode": data.get("opcode"),
        "flags": str(data.get("flags") or "").split(),
        "edns_flags": str(edns.get("flags") or "").split() if isinstance(edns, dict) else [],
        "ede": ede_text,
        "question": section("QUESTION_SECTION"),
        "answer": section("ANSWER_SECTION"),
        "authority": section("AUTHORITY_SECTION"),
        "additional": section("ADDITIONAL_SECTION"),
        "server": f"{server}#{port}" if server else None,
        "server_address": server,
        "protocol": msg.get("socket_protocol"),
        "query_time_ms": _ms_between(msg.get("query_time"), msg.get("response_time")),
        "message_size": msg.get("message_size"),
    }


def parse_dig_yaml(text: str) -> dict[str, Any]:
    """Parse ``dig +yaml`` output (one or more messages, e.g. with +trace)."""
    start = text.find("- type:")
    if start < 0:
        raise miniyaml.YamlError("no YAML document found")
    docs = miniyaml.loads(text[start:])
    if not isinstance(docs, list):
        raise miniyaml.YamlError("unexpected YAML structure")
    messages: list[dict[str, Any]] = []
    errors: list[str] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("type") == "MESSAGE" and isinstance(doc.get("message"), dict):
            messages.append(_message_summary(doc["message"]))
        elif doc.get("type") == "DIG_ERROR":
            errors.append(str(doc.get("message", "")).strip())
    return {"messages": messages, "errors": errors}


# ------------------------------------------------------------------ text output (fallback)
_HEADER_RE = re.compile(r";; ->>HEADER<<- opcode: (\w+), status: (\w+), id: (\d+)")
_FLAGS_RE = re.compile(r";; flags: ([a-z ]*);")
_TIME_RE = re.compile(r";; Query time: (\d+) msec")
_SERVER_RE = re.compile(r";; SERVER: (\S+?)(?:\((\S+)\))? \((\w+)\)")
_SECTION_RE = re.compile(r";; (QUESTION|ANSWER|AUTHORITY|ADDITIONAL) SECTION:")


def parse_dig_text(text: str) -> dict[str, Any]:
    """Parse classic ``dig`` text output (used when +yaml is unavailable)."""
    msg: dict[str, Any] = {
        "kind": "RESPONSE", "status": None, "opcode": None, "flags": [], "edns_flags": [],
        "ede": None, "question": [], "answer": [], "authority": [], "additional": [],
        "server": None, "server_address": None, "protocol": None, "query_time_ms": None,
        "message_size": None,
    }  # fmt: skip
    section = None
    errors = []
    for line in text.splitlines():
        if m := _HEADER_RE.search(line):
            msg["opcode"], msg["status"] = m.group(1), m.group(2)
        elif m := _FLAGS_RE.search(line):
            msg["flags"] = m.group(1).split()
        elif m := _TIME_RE.search(line):
            msg["query_time_ms"] = float(m.group(1))
        elif m := _SERVER_RE.search(line):
            msg["server"] = m.group(1)
            msg["server_address"] = m.group(1).split("#")[0]
            msg["protocol"] = m.group(3)
        elif m := _SECTION_RE.match(line):
            section = m.group(1).lower()
        elif line.startswith(";; communications error") or "no servers could be reached" in line:
            errors.append(line.lstrip("; ").strip())
        elif not line.strip():
            section = None
        elif section and line.startswith(";") and section == "question":
            msg["question"].append(parse_record(line.lstrip(";")))
        elif section and not line.startswith(";"):
            msg[section].append(parse_record(line))
    return {"messages": [msg] if msg["status"] else [], "errors": errors}
