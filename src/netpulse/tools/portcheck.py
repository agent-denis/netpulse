# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""TCP port check for one host and a few ports (a checker, not a scanner)."""

from __future__ import annotations

import errno
import socket
import threading
import time
from typing import Any

from netpulse import validators as v
from netpulse.jobs import JobContext
from netpulse.tools.base import Params, Summary, Tool

PRESETS: dict[str, list[int]] = {
    "web": [80, 443],
    "mail": [25, 465, 587, 110, 995, 143, 993],
    "ssh": [22],
}
SERVICES = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns", 80: "http", 110: "pop3",
    143: "imap", 443: "https", 465: "smtps", 587: "submission", 993: "imaps", 995: "pop3s",
    3306: "mysql", 3389: "rdp", 5432: "postgresql", 6379: "redis", 8080: "http-alt",
    8443: "https-alt",
}  # fmt: skip
FAMILIES = ("auto", "4", "6")
MAX_PORTS = 10


def validate(params: Params) -> Params:
    preset = v.choice(params.get("preset"), [*PRESETS, "custom"], "preset", default="custom")
    ports = (
        PRESETS[preset]
        if preset != "custom"
        else v.port_list(params.get("ports"), "ports", max_ports=MAX_PORTS)
    )
    return {
        "host": v.host_or_ip(params.get("host"), "host"),
        "preset": preset,
        "ports": ports if preset == "custom" else list(PRESETS[preset]),
        "timeout": v.float_range(params.get("timeout"), 0.5, 10.0, "timeout", default=3.0),
        "family": v.choice(params.get("family"), FAMILIES, "family", default="auto"),
    }


def build_argv(params: Params) -> list[str]:
    """No external command: this tool uses Python sockets. Returned for display only."""
    p = validate(params)
    return ["tcp-connect", p["host"], *map(str, p["ports"])]


def timeout(params: Params) -> float:
    return params["timeout"] * 2 + 15


def resolve(host: str, family: str) -> list[tuple[int, str]]:
    fam = {"auto": socket.AF_UNSPEC, "4": socket.AF_INET, "6": socket.AF_INET6}[family]
    infos = socket.getaddrinfo(host, None, fam, socket.SOCK_STREAM)
    seen: list[tuple[int, str]] = []
    for af, _, _, _, sockaddr in infos:
        item = (af, str(sockaddr[0]))
        if item not in seen:
            seen.append(item)
    return seen


def check_port(af: int, address: str, port: int, wait: float) -> dict[str, Any]:
    """Try one TCP connect. open / closed / filtered / error, with the connect time."""
    sock = socket.socket(af, socket.SOCK_STREAM)
    sock.settimeout(wait)
    t0 = time.perf_counter()
    try:
        sock.connect((address, port))
        state, detail = "open", "connection accepted"
    except ConnectionRefusedError:
        state, detail = "closed", "connection refused (nothing listening)"
    except TimeoutError:
        state, detail = "filtered", f"no answer within {wait:g} s (dropped by a firewall?)"
    except OSError as exc:
        if exc.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH):
            state, detail = "filtered", exc.strerror or "unreachable"
        else:
            state, detail = "error", exc.strerror or str(exc)
    finally:
        sock.close()
    ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "port": port,
        "service": SERVICES.get(port, ""),
        "state": state,
        "time_ms": ms if state in ("open", "closed") else None,
        "detail": detail,
        "address": address,
    }


def summarize(host: str, address: str | None, results: list[dict[str, Any]]) -> Summary:
    open_ports = [r["port"] for r in results if r["state"] == "open"]
    summary: Summary = {
        "host": host,
        "address": address,
        "results": sorted(results, key=lambda r: r["port"]),
        "open": open_ports,
    }
    if not results:
        return summary
    if open_ports:
        summary["status"] = "ok" if len(open_ports) == len(results) else "warning"
        summary["message"] = f"{len(open_ports)} of {len(results)} ports open"
    else:
        summary["status"] = "warning"
        summary["message"] = "no open ports"
    return summary


def run(ctx: JobContext, params: Params) -> Summary:
    p = params
    ctx.job.argv_display.append(build_argv(p))
    try:
        addresses = resolve(p["host"], p["family"])
    except socket.gaierror as exc:
        ctx.output(f"cannot resolve {p['host']}: {exc.strerror}\n")
        return {"status": "error", "message": f"cannot resolve {p['host']}: {exc.strerror}",
                "results": [], "host": p["host"]}  # fmt: skip
    af, address = addresses[0]
    ctx.output(f"Checking {p['host']} ({address}), TCP ports {', '.join(map(str, p['ports']))}\n")
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def one(port: int) -> None:
        if ctx.cancelled:
            return
        r = check_port(af, address, port, p["timeout"])
        with lock:
            results.append(r)
            t = f" {r['time_ms']} ms" if r["time_ms"] is not None else ""
            ctx.output(f"{port}/tcp {r['state']:<8}{t}  {r['service']}  ({r['detail']})\n")
            ctx.summary(summarize(p["host"], address, list(results)))

    threads = [threading.Thread(target=one, args=(port,), daemon=True) for port in p["ports"]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ctx.check_cancelled()
    summary = summarize(p["host"], address, results)
    summary["other_addresses"] = [a for _, a in addresses[1:]]
    return summary


TOOL = Tool(
    name="portcheck",
    title="TCP port check",
    group="Connectivity",
    description="Check whether TCP ports on one host are open, closed or filtered.",
    validate=validate,
    run=run,
    timeout=timeout,
    binaries=(),
    target=lambda p: f"{p['host']} {','.join(map(str, p['ports']))}",
    notes=(
        "Checks at most 10 ports on one host. It is a reachability checker, not a port scanner.",
        "Some networks (mobile hotspots, captive portals, transparent proxies) accept every "
        "connection themselves, so 'open' can mean the network answered, not the host.",
    ),
)
