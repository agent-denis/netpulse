# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Quick diagnose: ping, DNS A/AAAA, traceroute and an HTTP check for one host, together."""

from __future__ import annotations

import threading
from collections.abc import Callable

from netpulse import detect
from netpulse import validators as v
from netpulse.jobs import JobContext, ToolMissingError
from netpulse.tools import dig, httpcheck, ping, traceroute
from netpulse.tools.base import Params, Summary, Tool

CHECKS = ("dns_a", "dns_aaaa", "ping", "traceroute", "http")
TITLES = {
    "dns_a": "DNS (A)",
    "dns_aaaa": "DNS (AAAA)",
    "ping": "Ping",
    "traceroute": "Traceroute",
    "http": "HTTP(S)",
}


def validate(params: Params) -> Params:
    return {"host": v.host_or_ip(params.get("host"), "host")}


def plan(host: str) -> dict[str, tuple[list[str] | None, Callable[[str], Summary], float]]:
    """check → (argv or None if skipped, parser, timeout)."""
    is_ip = v.is_ip(host)
    url = (
        f"http://[{host}]/" if ":" in host else (f"http://{host}/" if is_ip else f"https://{host}/")
    )
    tr_params = traceroute.validate({"host": host, "max_hops": 30, "probes": 2})
    http_params = httpcheck.validate({"url": url, "timeout": 15})
    ping_params = ping.validate({"host": host, "count": 4, "interval": 0.5})
    out: dict[str, tuple[list[str] | None, Callable[[str], Summary], float]] = {
        "dns_a": (
            None if is_ip else dig.build_argv({"name": host, "type": "A"}),
            dig.parse,
            dig.timeout({}),
        ),
        "dns_aaaa": (
            None if is_ip else dig.build_argv({"name": host, "type": "AAAA"}),
            dig.parse,
            dig.timeout({}),
        ),
        "ping": (ping.build_argv(ping_params), ping.parse, ping.timeout(ping_params)),
        "traceroute": (
            traceroute.build_argv(tr_params),
            traceroute.parse,
            traceroute.timeout(tr_params),
        ),
        "http": (
            httpcheck.build_argv(http_params),
            httpcheck.parse,
            httpcheck.timeout(http_params),
        ),
    }
    return out


def build_argv(params: Params) -> list[list[str]]:  # several commands
    p = validate(params)
    return [argv for argv, _, _ in plan(p["host"]).values() if argv]


def timeout(params: Params) -> float:
    return max(t for _, _, t in plan(params["host"]).values()) + 10


def brief(check: str, s: Summary) -> str:
    """A one-line finding per check, for the report."""
    if s.get("skipped"):
        return s["message"]
    if check.startswith("dns"):
        recs = [r["data"] for r in s.get("answer", []) if r.get("type") in ("A", "AAAA")]
        if recs:
            return f"{len(recs)} address(es): {', '.join(recs[:4])}{' …' if len(recs) > 4 else ''}"
        return s.get("message", "")
    if check == "ping" and s.get("avg") is not None:
        return f"{s.get('loss_pct', 0):g}% loss, average {s['avg']:.1f} ms"
    if check == "traceroute" and s.get("hops"):
        reached = "reached" if s.get("reached") else "not reached"
        return f"{reached} in {s.get('hop_count')} hops"
    if check == "http" and s.get("http_code"):
        t = s.get("timing", {})
        return (
            f"HTTP {s['http_code']} from {s.get('url_effective')} in {t.get('total_ms', 0):.0f} ms"
        )
    return s.get("message", "")


def overall(checks: dict[str, Summary]) -> tuple[str, str]:
    states = {k: s.get("status") for k, s in checks.items() if not s.get("skipped")}
    problems = [TITLES[k] for k, st in states.items() if st == "error"]
    warnings = [TITLES[k] for k, st in states.items() if st == "warning"]
    if problems:
        return "error", f"problems with: {', '.join(problems)}"
    if warnings:
        return "warning", f"warnings for: {', '.join(warnings)}"
    return "ok", "everything looks fine"


def report(host: str, checks: dict[str, Summary], pending: list[str]) -> Summary:
    rows = []
    for name in CHECKS:
        s = checks.get(name)
        if s is None:
            rows.append(
                {"check": name, "title": TITLES[name], "status": "running", "finding": "running…"}
            )
        else:
            st = "skipped" if s.get("skipped") else s.get("status", "error")
            rows.append(
                {"check": name, "title": TITLES[name], "status": st, "finding": brief(name, s)}
            )
    status, message = overall(checks) if not pending else ("ok", "running…")
    return {
        "host": host,
        "rows": rows,
        "checks": checks,
        "pending": pending,
        "status": status,
        "message": message,
    }


def run(ctx: JobContext, params: Params) -> Summary:
    host = params["host"]
    steps = plan(host)
    checks: dict[str, Summary] = {}
    lock = threading.Lock()

    def publish() -> None:
        pending = [c for c in CHECKS if c not in checks]
        ctx.summary(report(host, dict(checks), pending))

    def one(name: str) -> None:
        argv, parser, limit = steps[name]
        if argv is None:
            s: Summary = {
                "skipped": True,
                "status": "ok",
                "message": "skipped: the target is an IP address",
            }
        elif not detect.which(argv[2] if argv[0] == "stdbuf" else argv[0]):
            hint = detect.install_hint([argv[0]])
            s = {
                "skipped": True,
                "status": "ok",
                "message": f"skipped: {argv[0]} is missing ({hint})",
            }
        else:
            try:
                r = ctx.run(argv, timeout=limit, label=TITLES[name])
                s = parser(r.output)
                if r.timed_out:
                    s.update(status="error", message="timed out")
            except ToolMissingError as exc:
                s = {"skipped": True, "status": "ok", "message": f"skipped: {exc} is not installed"}
            except Exception as exc:
                s = {"status": "error", "message": str(exc)}
        with lock:
            checks[name] = s
            publish()

    publish()
    threads = [threading.Thread(target=one, args=(name,), daemon=True) for name in CHECKS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ctx.check_cancelled()
    return report(host, checks, [])


def parse(output: str) -> Summary:
    """Quick diagnose combines other tools' parsers; there is no single output to parse."""
    return {"status": "ok", "message": "", "rows": []}


TOOL = Tool(
    name="diagnose",
    title="Quick diagnose",
    group="Utilities",
    description="Run DNS, ping, traceroute and an HTTP check for one host at once, "
    "and get a one-page report.",
    validate=validate,
    run=run,
    timeout=timeout,
    binaries=("ping",),
)
