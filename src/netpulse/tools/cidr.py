# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""CIDR / subnet calculator (pure ``ipaddress``, no external calls)."""

from __future__ import annotations

import ipaddress
from typing import Any

from netpulse import validators as v
from netpulse.jobs import JobContext
from netpulse.tools.base import Params, Summary, Tool

MAX_SUBNETS = 256

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def validate(params: Params) -> Params:
    iface = v.cidr(params.get("network"), "network")
    split = params.get("split")
    split_prefix = None
    if split not in (None, ""):
        split_prefix = v.int_range(split, 0, 128, "split", default=0)
        if split_prefix <= iface.network.prefixlen or split_prefix > iface.max_prefixlen:
            raise v.ValidationError(
                "split",
                f"must be between /{iface.network.prefixlen + 1} and /{iface.max_prefixlen}",
            )
    return {"network": str(iface.with_prefixlen), "split": split_prefix if split_prefix else ""}


def build_argv(params: Params) -> list[str]:
    """No external command (pure Python). Returned for display only."""
    p = validate(params)
    return ["cidr", p["network"], *([f"/{p['split']}"] if p["split"] else [])]


def timeout(params: Params) -> float:
    return 10.0


def classify(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> list[str]:
    kinds = []
    for attr, label in (
        ("is_loopback", "loopback"),
        ("is_link_local", "link-local"),
        ("is_multicast", "multicast"),
        ("is_private", "private"),
        ("is_global", "public (global)"),
        ("is_reserved", "reserved"),
        ("is_unspecified", "unspecified"),
    ):
        if getattr(addr, attr, False):
            kinds.append(label)
    if isinstance(addr, ipaddress.IPv4Address) and addr in ipaddress.ip_network("100.64.0.0/10"):
        kinds.append("carrier-grade NAT (RFC 6598)")
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        kinds.append(f"IPv4-mapped ({addr.ipv4_mapped})")
    return kinds or ["other"]


def _bits(mask: ipaddress.IPv4Address) -> str:
    raw = f"{int(mask):032b}"
    return ".".join(raw[i : i + 8] for i in range(0, 32, 8))


def calculate(network: str, split: int | str = "") -> Summary:
    iface = ipaddress.ip_interface(network)
    net: Network = iface.network
    total = net.num_addresses
    out: dict[str, Any] = {
        "input": network,
        "version": net.version,
        "address": str(iface.ip),
        "network": str(net),
        "prefix": net.prefixlen,
        "total_addresses": f"{total:,}",
        "size": f"2^{net.max_prefixlen - net.prefixlen}",
        "address_kind": classify(iface.ip),
        "reverse_zone": net.network_address.reverse_pointer,
    }
    if net.version == 4:
        hosts = total - 2 if net.prefixlen < 31 else total
        first = net.network_address + (1 if net.prefixlen < 31 else 0)
        last = net.broadcast_address - (1 if net.prefixlen < 31 else 0)
        out.update(
            netmask=str(net.netmask),
            netmask_bits=_bits(net.netmask),
            wildcard=str(net.hostmask),
            broadcast=str(net.broadcast_address) if net.prefixlen < 31 else None,
            first_host=str(first),
            last_host=str(last),
            usable_hosts=f"{hosts:,}",
        )
    else:
        out.update(
            first_address=str(net.network_address),
            last_address=str(net.broadcast_address),
            expanded=iface.ip.exploded,
            compressed=iface.ip.compressed,
            network_expanded=net.network_address.exploded,
        )
    if iface.ip != net.network_address:
        out["note"] = f"{iface.ip} is a host address inside {net}"
    if split:
        new_prefix = int(split)
        count = 2 ** (new_prefix - net.prefixlen)
        subnets = []
        for i, sub in enumerate(net.subnets(new_prefix=new_prefix)):
            if i >= MAX_SUBNETS:
                break
            subnets.append(
                {
                    "subnet": str(sub),
                    "first": str(sub.network_address),
                    "last": str(sub.broadcast_address),
                    "addresses": f"{sub.num_addresses:,}",
                }
            )
        out["subnets"] = subnets
        out["subnet_count"] = f"{count:,}"
        out["subnets_truncated"] = count > MAX_SUBNETS
    out["status"] = "ok"
    out["message"] = f"{net} · {total:,} addresses"
    return out


def run(ctx: JobContext, params: Params) -> Summary:
    ctx.job.argv_display.append(build_argv(params))
    summary = calculate(params["network"], params["split"])
    for key, value in summary.items():
        if key in ("subnets", "status", "message"):
            continue
        ctx.output(
            f"{key.replace('_', ' ')}: {', '.join(value) if isinstance(value, list) else value}\n"
        )
    for sub in summary.get("subnets", []):
        ctx.output(f"subnet {sub['subnet']}  {sub['first']} to {sub['last']}\n")
    return summary


def parse(output: str) -> Summary:
    """Not used for parsing tool output; computes the summary for a network string."""
    return calculate(output.strip())


TOOL = Tool(
    name="cidr",
    title="Subnet calculator",
    group="Utilities",
    description="Network, mask, host range and size for an IPv4 or IPv6 network. Works offline.",
    validate=validate,
    run=run,
    timeout=timeout,
    binaries=(),
    target=lambda p: p["network"],
)
