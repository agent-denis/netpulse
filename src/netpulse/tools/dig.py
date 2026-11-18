# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""dig (bind-utils), parsed from ``+yaml`` output."""

from __future__ import annotations

from typing import Any

from netpulse import miniyaml
from netpulse import validators as v
from netpulse.tools import dnscommon as dc
from netpulse.tools.base import Params, Summary, Tool, command_runner

TIMEOUT_S = 5
TRIES = 2


def validate(params: Params) -> Params:
    rtype = v.choice(params.get("type"), dc.RECORD_TYPES, "type", default="A")
    return {
        "name": dc.dns_name_or_ip(params.get("name"), rtype),
        "type": rtype,
        "resolver": v.choice(params.get("resolver"), dc.RESOLVERS, "resolver", default="system"),
        "custom": (
            v.host_or_ip(params.get("custom"), "custom")
            if params.get("resolver") == "custom"
            else ""
        ),
        "short": v.boolean(params.get("short"), "short"),
        "trace": v.boolean(params.get("trace"), "trace"),
        "dnssec": v.boolean(params.get("dnssec"), "dnssec"),
        "tcp": v.boolean(params.get("tcp"), "tcp"),
    }


def server_of(p: Params) -> str | None:
    if p["resolver"] == "system":
        return None
    return p["custom"] if p["resolver"] == "custom" else p["resolver"]


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    # -r: ignore ~/.digrc so the output format is predictable.
    argv = ["dig", "-r"]
    if not p["short"]:
        argv.append("+yaml")
    argv += [f"+timeout={TIMEOUT_S}", f"+tries={TRIES}"]
    server = server_of(p)
    if server:
        argv.append(f"@{server}")
    for flag in ("short", "trace", "dnssec", "tcp"):
        if p[flag]:
            argv.append(f"+{flag}")
    # -t / -q mark type and name explicitly, so neither can be read as an option.
    return [*argv, "-t", p["type"], "-q", p["name"]]


def timeout(params: Params) -> float:
    return 120.0 if params.get("trace") else TIMEOUT_S * TRIES * 3 + 10


def summarize(parsed: dict[str, Any]) -> Summary:
    """Turn parsed messages into the tool summary (the last message is the answer)."""
    messages = parsed["messages"]
    errors = parsed["errors"]
    if not messages:
        return {
            "status": "error",
            "message": "; ".join(errors) or "no response",
            "rcode": None,
            "chain": [],
        }
    final = messages[-1]
    summary: Summary = {
        "rcode": final["status"],
        "flags": final["flags"],
        "edns_flags": final["edns_flags"],
        "ede": final["ede"],
        "question": final["question"],
        "answer": final["answer"],
        "authority": final["authority"],
        "additional": final["additional"],
        "server": final["server"],
        "protocol": final["protocol"],
        "query_time_ms": final["query_time_ms"],
        "message_size": final["message_size"],
        "answer_count": len(final["answer"]),
        "authenticated": "ad" in final["flags"],
        "errors": errors,
    }
    if len(messages) > 1:  # +trace: the delegation chain
        summary["chain"] = [
            {
                "step": i + 1,
                "server": m["server"],
                "kind": m["kind"],
                "status": m["status"],
                "zone": (m["authority"] or m["answer"] or [{"name": ""}])[0]["name"],
                "records": len(m["answer"]) + len(m["authority"]),
                "query_time_ms": m["query_time_ms"],
            }
            for i, m in enumerate(messages)
        ]
    rcode = final["status"]
    if rcode in dc.ERROR_RCODES:
        summary["status"] = "error"
        summary["message"] = f"{rcode}" + (f" ({final['ede']})" if final["ede"] else "")
    elif rcode in dc.NEGATIVE_RCODES:
        summary["status"] = "warning"
        summary["message"] = f"{rcode}: the name does not exist"
    elif not final["answer"]:
        summary["status"] = "warning"
        summary["message"] = "NOERROR but no records of this type (NODATA)"
    else:
        summary["status"] = "ok"
        n = len(final["answer"])
        summary["message"] = f"{rcode}, {n} record{'s' if n != 1 else ''}"
    return summary


def parse_short(output: str) -> Summary:
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    errors = [ln.lstrip("; ").strip() for ln in lines if ln.startswith(";;")]
    values = [ln for ln in lines if not ln.startswith(";")]
    if errors and not values:
        return {"status": "error", "message": "; ".join(errors), "short": [], "rcode": None}
    summary: Summary = {"short": values, "answer_count": len(values), "rcode": None}
    if values:
        summary["status"], summary["message"] = "ok", f"{len(values)} value(s)"
    else:
        summary["status"] = "warning"
        summary["message"] = "no records (+short does not show the status code)"
    return summary


def parse(output: str) -> Summary:
    if "- type:" in output:
        try:
            return summarize(dc.parse_dig_yaml(output))
        except miniyaml.YamlError:
            pass
    if ";; ->>HEADER<<-" in output or ";; communications error" in output:
        return summarize(dc.parse_dig_text(output))
    return parse_short(output)


TOOL = Tool(
    name="dig",
    title="dig",
    group="DNS",
    description="Query DNS records with full detail: sections, TTLs, flags and timing.",
    validate=validate,
    run=command_runner(build_argv, parse, timeout),
    timeout=timeout,
    binaries=("dig",),
    target=lambda p: f"{p['name']} {p['type']}",
    notes=(
        "ANY queries: many servers now return a minimal answer (RFC 8482), so ANY does not "
        "list every record. Query the record types you need instead.",
    ),
)
