# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""traceroute, with tracepath (iputils) as a fallback."""

from __future__ import annotations

import re
from typing import Any

from netpulse import detect
from netpulse import validators as v
from netpulse.jobs import JobContext
from netpulse.tools.base import Params, Summary, Tool

FAMILIES = ("auto", "4", "6")
MODES = ("udp", "icmp", "tcp")
WAIT_S = 3

_TR_HEADER_RE = re.compile(r"^traceroute to (\S+) \(([^)]+)\), (\d+) hops max")
_TR_HOP_RE = re.compile(r"^\s*(\d+)\s+(.*)$")
_TP_HOP_RE = re.compile(r"^\s*(\d+)(\?)?:\s+(.*)$")
_TP_RTT_RE = re.compile(r"^(\S+)\s+([\d.]+)ms(.*)$")
_IP_RE = re.compile(r"^[0-9a-fA-F:.]+$")

PRIV_ERRORS = ("not enough privileges", "Operation not permitted")


def validate(params: Params) -> Params:
    return {
        "host": v.host_or_ip(params.get("host"), "host"),
        "max_hops": v.int_range(params.get("max_hops"), 1, 64, "max_hops", default=30),
        "probes": v.int_range(params.get("probes"), 1, 5, "probes", default=3),
        "family": v.choice(params.get("family"), FAMILIES, "family", default="auto"),
        "mode": v.choice(params.get("mode"), MODES, "mode", default="udp"),
        "resolve": v.boolean(params.get("resolve"), "resolve", default=True),
    }


def backend() -> str:
    """traceroute if installed, else tracepath."""
    return "traceroute" if detect.which("traceroute") else "tracepath"


def build_argv(params: Params, use: str | None = None) -> list[str]:
    p = validate(params)
    use = use or backend()
    fam = [f"-{p['family']}"] if p["family"] != "auto" else []
    if use == "tracepath":
        # tracepath only does UDP; it writes through stdio, so force line buffering.
        argv = ["stdbuf", "-oL", "tracepath", *(["-n"] if not p["resolve"] else [])]
        return [*argv, "-m", str(p["max_hops"]), *fam, "--", p["host"]]
    argv = ["traceroute", *(["-n"] if not p["resolve"] else []), *fam]
    argv += {"udp": [], "icmp": ["-I"], "tcp": ["-T"]}[p["mode"]]
    argv += ["-m", str(p["max_hops"]), "-q", str(p["probes"]), "-w", str(WAIT_S)]
    return [*argv, "--", p["host"]]


def timeout(params: Params) -> float:
    return min(600.0, params["max_hops"] * params["probes"] * WAIT_S / 2 + 30)


def _hop(n: int) -> dict[str, Any]:
    return {"hop": n, "probes": [], "hosts": [], "annotations": []}


def _finish_hop(hop: dict[str, Any]) -> dict[str, Any]:
    probes = hop["probes"]
    rtts = [p["rtt"] for p in probes if p.get("rtt") is not None]
    hosts: list[dict[str, str | None]] = []
    for p in probes:
        if not (p.get("ip") or p.get("name")):
            continue
        if not any(h["ip"] == p.get("ip") and h["name"] == p.get("name") for h in hosts):
            hosts.append({"name": p.get("name"), "ip": p.get("ip")})
    hop["hosts"] = hosts
    hop["rtts"] = rtts
    hop["sent"] = len(probes)
    hop["lost"] = sum(1 for p in probes if p.get("rtt") is None)
    hop["loss_pct"] = round(100 * hop["lost"] / len(probes), 1) if probes else None
    hop["avg"] = round(sum(rtts) / len(rtts), 3) if rtts else None
    hop["hostname"] = hosts[0]["name"] if hosts else None
    hop["ip"] = hosts[0]["ip"] if hosts else None
    return hop


def _parse_tr_hop(n: int, rest: str) -> dict[str, Any]:
    hop = _hop(n)
    tokens = rest.split()
    cur: dict[str, str | None] = {"name": None, "ip": None}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "*":
            hop["probes"].append({"rtt": None})
        elif i + 1 < len(tokens) and tokens[i + 1] == "ms":
            try:
                rtt = float(tok)
            except ValueError:
                rtt = None
            hop["probes"].append({"rtt": rtt, "name": cur["name"], "ip": cur["ip"]})
            i += 1
        elif tok.startswith("!"):
            hop["annotations"].append(tok)
        elif tok.startswith("(") and tok.endswith(")"):
            cur["ip"] = tok[1:-1]
        else:
            cur = {
                "name": None if _IP_RE.match(tok) else tok,
                "ip": tok if _IP_RE.match(tok) else None,
            }
        i += 1
    return hop


def parse_traceroute(output: str) -> Summary:
    target = address = None
    max_hops = None
    hops: list[dict[str, Any]] = []
    errors: list[str] = []
    for line in output.splitlines():
        if m := _TR_HEADER_RE.match(line):
            target, address, max_hops = m.group(1), m.group(2), int(m.group(3))
        elif (m := _TR_HOP_RE.match(line)) and not line.startswith("traceroute"):
            hops.append(_finish_hop(_parse_tr_hop(int(m.group(1)), m.group(2))))
        elif line.strip() and not line.startswith("$ "):
            errors.append(line.strip())
    return _summary("traceroute", target, address, max_hops, hops, errors)


def parse_tracepath(output: str) -> Summary:
    by_hop: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    reached = False
    pmtu = None
    for line in output.splitlines():
        stripped = line.strip()
        if m := _TP_HOP_RE.match(line):
            n, probe_marker, rest = int(m.group(1)), m.group(2), m.group(3)
            if probe_marker or rest.startswith("[LOCALHOST]"):
                continue
            hop = by_hop.setdefault(n, _hop(n))
            if rest.startswith("no reply"):
                hop["probes"].append({"rtt": None})
                continue
            if rm := _TP_RTT_RE.match(rest):
                name = rm.group(1)
                is_ip = bool(_IP_RE.match(name))
                # tracepath shows either a name or an address, not both
                hop["probes"].append(
                    {"rtt": float(rm.group(2)), "name": None if is_ip else name,
                     "ip": name if is_ip else None}
                )  # fmt: skip
                extra = rm.group(3)
                if "reached" in extra:
                    reached = True
                if pm := re.search(r"pmtu (\d+)", extra):
                    pmtu = int(pm.group(1))
                if am := re.search(r"asymm\s+(\d+)", extra):
                    hop["annotations"].append(f"asymm {am.group(1)}")
        elif stripped.startswith("Resume:"):
            if pm := re.search(r"pmtu (\d+)", stripped):
                pmtu = int(pm.group(1))
            if "hops" in stripped:
                reached = True
        elif stripped.startswith("Too many hops"):
            continue
        elif stripped.startswith("tracepath:") or "unreachable" in stripped.lower():
            errors.append(stripped)
    hops = [_finish_hop(by_hop[n]) for n in sorted(by_hop)]
    summary = _summary("tracepath", None, None, None, hops, errors, reached=reached)
    summary["pmtu"] = pmtu
    return summary


def _summary(
    backend_name: str,
    target: str | None,
    address: str | None,
    max_hops: int | None,
    hops: list[dict[str, Any]],
    errors: list[str],
    reached: bool | None = None,
) -> Summary:
    if reached is None:
        last = hops[-1] if hops else None
        reached = bool(last and address and any(h["ip"] == address for h in last["hosts"]))
    summary: Summary = {
        "backend": backend_name,
        "target": target,
        "address": address,
        "max_hops": max_hops,
        "hops": hops,
        "hop_count": len(hops),
        "reached": reached,
    }
    privilege = any(any(p in e for p in PRIV_ERRORS) for e in errors)
    if errors and not hops:
        msg = "; ".join(errors)
        if privilege:
            msg = "this mode needs root privileges (raw sockets); use UDP or ICMP mode instead"
        summary["status"], summary["message"] = "error", msg
    elif reached:
        summary["status"] = "ok"
        n = len(hops)
        summary["message"] = f"reached the destination in {n} hop{'s' if n != 1 else ''}"
    elif hops:
        summary["status"] = "warning"
        summary["message"] = f"destination not reached within {len(hops)} hops"
    else:
        summary["status"] = "ok"
    return summary


def parse(output: str) -> Summary:
    if "tracepath:" in output or re.search(r"^\s*\d+\??:\s", output, re.M):
        return parse_tracepath(output)
    return parse_traceroute(output)


def run(ctx: JobContext, params: Params) -> Summary:
    use = backend()
    argv = build_argv(params, use)
    if use == "tracepath":
        ctx.note("traceroute is not installed; using tracepath (UDP only)")
    parser = parse_tracepath if use == "tracepath" else parse_traceroute
    buf: list[str] = []

    def on_line(line: str) -> None:
        buf.append(line)
        ctx.summary(parser("".join(buf)))

    result = ctx.run(argv, timeout=timeout(params), on_line=on_line)
    summary = parser(result.output)
    summary["exit_code"] = result.returncode
    if result.timed_out:
        summary["status"], summary["message"] = "error", "the command timed out"
    return summary


TOOL = Tool(
    name="traceroute",
    title="Traceroute",
    group="Connectivity",
    description="Show the path packets take to a host, hop by hop.",
    validate=validate,
    run=run,
    timeout=timeout,
    binaries=("traceroute", "tracepath"),
    notes=(
        "UDP (default) and ICMP work without root. TCP mode needs root privileges "
        "(raw sockets). NetPulse never asks for root, so TCP mode will fail unless you "
        "run traceroute with extra capabilities.",
    ),
)
