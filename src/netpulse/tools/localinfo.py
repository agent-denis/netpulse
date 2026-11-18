# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Local network information: interfaces, routes, DNS configuration, listening sockets."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from netpulse import detect
from netpulse import validators as v
from netpulse.jobs import JobContext
from netpulse.tools.base import Params, Summary, Tool

ADDR_ARGV = ["ip", "-j", "addr", "show"]
ROUTE4_ARGV = ["ip", "-j", "-4", "route", "show"]
ROUTE6_ARGV = ["ip", "-j", "-6", "route", "show"]
DNS_ARGV = ["resolvectl", "status", "--no-pager"]
SOCKETS_ARGV = ["ss", "-H", "-t", "-u", "-l", "-n"]


def validate(params: Params) -> Params:
    return {"sockets": v.boolean(params.get("sockets"), "sockets", default=False)}


def build_argv(params: Params) -> list[list[str]]:  # several commands
    p = validate(params)
    argvs = [ADDR_ARGV, ROUTE4_ARGV, ROUTE6_ARGV, DNS_ARGV]
    return [*argvs, SOCKETS_ARGV] if p["sockets"] else argvs


def timeout(params: Params) -> float:
    return 30.0


def _json(text: str) -> Any:
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start < 0:
        return []
    try:
        return json.loads(text[start:])
    except ValueError:
        return []


def parse_addr(text: str) -> list[dict[str, Any]]:
    out = []
    for link in _json(text):
        out.append(
            {
                "name": link.get("ifname"),
                "state": link.get("operstate"),
                "mac": link.get("address") if link.get("link_type") != "loopback" else None,
                "mtu": link.get("mtu"),
                "type": link.get("link_type"),
                "flags": link.get("flags", []),
                "addresses": [
                    {
                        "family": "IPv6" if a.get("family") == "inet6" else "IPv4",
                        "address": a.get("local"),
                        "prefix": a.get("prefixlen"),
                        "scope": a.get("scope"),
                        "dynamic": bool(a.get("dynamic")),
                    }
                    for a in link.get("addr_info", [])
                ],
            }
        )
    return out


def parse_routes(text: str, family: str) -> list[dict[str, Any]]:
    return [
        {
            "family": family,
            "dst": r.get("dst"),
            "gateway": r.get("gateway"),
            "dev": r.get("dev"),
            "protocol": r.get("protocol"),
            "metric": r.get("metric"),
            "src": r.get("prefsrc"),
        }
        for r in _json(text)
        if isinstance(r, dict)
    ]


def parse_resolvectl(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"global": {}, "links": [], "source": "resolvectl"}
    section: dict[str, Any] = result["global"]
    key = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if raw.startswith("Global"):
            section, key = result["global"], None
            continue
        if m := re.match(r"^Link (\d+) \(([^)]+)\)", raw):
            section = {"link": m.group(2), "index": int(m.group(1))}
            result["links"].append(section)
            key = None
            continue
        if m := re.match(r"^\s*([A-Za-z][A-Za-z .]+?):\s*(.*)$", raw):
            key = m.group(1).strip().lower().replace(" ", "_")
            section[key] = m.group(2).strip()
        elif key:  # continuation line
            section[key] = f"{section[key]} {raw.strip()}".strip()
    for sec in [result["global"], *result["links"]]:
        for k in ("dns_servers", "fallback_dns_servers", "dns_domain"):
            if k in sec:
                sec[k] = sec[k].split()
    return result


def parse_resolv_conf(text: str) -> dict[str, Any]:
    servers = re.findall(r"^\s*nameserver\s+(\S+)", text, re.M)
    search = re.findall(r"^\s*(?:search|domain)\s+(.+)$", text, re.M)
    return {"global": {"dns_servers": servers, "dns_domain": " ".join(search).split()},
            "links": [], "source": "/etc/resolv.conf"}  # fmt: skip


def parse_ss(text: str) -> list[dict[str, Any]]:
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] not in ("tcp", "udp"):
            continue
        local = parts[4]
        addr, _, port = local.rpartition(":")
        out.append({"proto": parts[0], "state": parts[1], "address": addr, "port": port})
    return sorted(out, key=lambda s: (s["proto"], int(s["port"]) if s["port"].isdigit() else 0))


def summarize(data: dict[str, Any]) -> Summary:
    interfaces = data.get("interfaces", [])
    routes = data.get("routes", [])
    gateways = [r for r in routes if r["dst"] == "default"]
    dns = data.get("dns") or {"global": {}, "links": []}
    servers: list[str] = list(dns["global"].get("dns_servers", []))
    for link in dns["links"]:
        for s in link.get("dns_servers", []):
            if s not in servers:
                servers.append(s)
    up = [i for i in interfaces if i["state"] in ("UP", "UNKNOWN") and i["type"] != "loopback"]
    summary: Summary = {
        "interfaces": interfaces,
        "routes": routes,
        "gateways": gateways,
        "dns": dns,
        "dns_servers": servers,
        "sockets": data.get("sockets"),
        "notes": data.get("notes", []),
    }
    if not gateways:
        summary["status"], summary["message"] = (
            "warning",
            "no default route: no internet access via this machine's routing table",
        )
    else:
        gw = ", ".join(f"{g['gateway']} via {g['dev']}" for g in gateways if g.get("gateway"))
        summary["status"] = "ok"
        summary["message"] = f"{len(up)} active interface(s); default gateway {gw or 'set'}"
    return summary


def run(ctx: JobContext, params: Params) -> Summary:
    data: dict[str, Any] = {"notes": []}
    if detect.which("ip"):
        data["interfaces"] = parse_addr(ctx.run(ADDR_ARGV, timeout=10, label="addr").output)
        data["routes"] = parse_routes(
            ctx.run(ROUTE4_ARGV, timeout=10, label="route").output, "IPv4"
        )
        data["routes"] += parse_routes(
            ctx.run(ROUTE6_ARGV, timeout=10, label="route6").output, "IPv6"
        )
    else:
        data["notes"].append("'ip' is not installed (sudo dnf install iproute)")
    ctx.summary(summarize(data))
    if detect.which("resolvectl"):
        r = ctx.run(DNS_ARGV, timeout=10, label="dns")
        if r.returncode == 0:
            data["dns"] = parse_resolvectl(r.output)
    if "dns" not in data:
        try:
            text = Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="replace")
            ctx.output(f"[dns] /etc/resolv.conf:\n{text}")
            data["dns"] = parse_resolv_conf(text)
        except OSError:
            data["notes"].append("no DNS configuration found")
    if params.get("sockets"):
        if detect.which("ss"):
            data["sockets"] = parse_ss(ctx.run(SOCKETS_ARGV, timeout=10, label="sockets").output)
        else:
            data["notes"].append("'ss' is not installed (sudo dnf install iproute)")
    return summarize(data)


def parse(output: str) -> Summary:
    """Parse ``ip -j addr`` output alone (the other parts have their own parsers)."""
    return summarize({"interfaces": parse_addr(output), "routes": []})


TOOL = Tool(
    name="localinfo",
    title="Local network",
    group="Local",
    description="Interfaces, addresses, routes, default gateway and DNS settings of this computer.",
    validate=validate,
    run=run,
    timeout=timeout,
    binaries=("ip",),
    target=lambda p: "this computer",
)
