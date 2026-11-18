# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Ask several resolvers the same question in parallel and compare the answers."""

from __future__ import annotations

import threading
from collections import Counter
from typing import Any

from netpulse import validators as v
from netpulse.jobs import JobContext
from netpulse.tools import dig
from netpulse.tools import dnscommon as dc
from netpulse.tools.base import Params, Summary, Tool

PRESETS = ("system", "1.1.1.1", "8.8.8.8", "9.9.9.9")
TYPES = tuple(t for t in dc.RECORD_TYPES if t != "ANY")
MAX_RESOLVERS = 8


def validate(params: Params) -> Params:
    rtype = v.choice(params.get("type"), TYPES, "type", default="A")
    resolvers: list[str] = []
    for key in PRESETS:
        if v.boolean(params.get(f"use_{key.replace('.', '_')}"), key, default=key != "system"):
            resolvers.append(key)
    extra = params.get("custom") or ""
    if not isinstance(extra, str):
        raise v.ValidationError("custom", "must be text")
    for item in [x for x in extra.replace(",", " ").split() if x]:
        server = v.host_or_ip(item, "custom")
        if server not in resolvers:
            resolvers.append(server)
    if len(resolvers) < 2:
        raise v.ValidationError("custom", "choose at least two resolvers to compare")
    if len(resolvers) > MAX_RESOLVERS:
        raise v.ValidationError("custom", f"at most {MAX_RESOLVERS} resolvers")
    return {
        "name": dc.dns_name_or_ip(params.get("name"), rtype),
        "type": rtype,
        "resolvers": resolvers,
        # keep the form state so "Run again" restores it
        **{f"use_{k.replace('.', '_')}": k in resolvers for k in PRESETS},
        "custom": " ".join(r for r in resolvers if r not in PRESETS),
    }


def build_argv(params: Params) -> list[list[str]]:  # type: ignore[override]
    """One dig command per resolver."""
    p = validate(params)
    out = []
    for resolver in p["resolvers"]:
        dig_params = {"name": p["name"], "type": p["type"], "resolver": "system"}
        if resolver != "system":
            dig_params.update(resolver="custom", custom=resolver)
        out.append(dig.build_argv(dig_params))
    return out


def timeout(params: Params) -> float:
    return dig.timeout({}) + 5


def _answer_set(summary: Summary) -> tuple[str, ...]:
    """Comparable answer: the record data, sorted (TTLs differ between caches)."""
    return tuple(sorted(f"{r['type']} {r['data']}" for r in summary.get("answer", [])))


def compare(results: dict[str, Summary]) -> Summary:
    rows: list[dict[str, Any]] = []
    sets = {name: (s.get("rcode"), _answer_set(s)) for name, s in results.items()}
    counts = Counter(sets.values())
    majority = counts.most_common(1)[0][0] if counts else None
    for name, s in results.items():
        ttls = [r["ttl"] for r in s.get("answer", []) if r.get("ttl") is not None]
        rows.append(
            {
                "resolver": name,
                "rcode": s.get("rcode"),
                "status": s.get("status"),
                "answers": [r["data"] for r in s.get("answer", [])],
                "min_ttl": min(ttls) if ttls else None,
                "query_time_ms": s.get("query_time_ms"),
                "server": s.get("server"),
                "matches": sets[name] == majority,
                "message": s.get("message"),
            }
        )
    differ = len(counts) > 1
    summary: Summary = {"rows": rows, "consistent": not differ, "groups": len(counts)}
    if any(r["status"] == "error" for r in rows):
        summary["status"] = "warning" if any(r["status"] != "error" for r in rows) else "error"
        failed = [r["resolver"] for r in rows if r["status"] == "error"]
        summary["message"] = f"query failed on {', '.join(failed)}"
    elif differ:
        summary["status"] = "warning"
        summary["message"] = f"resolvers disagree ({len(counts)} different answers)"
    else:
        summary["status"] = "ok"
        summary["message"] = f"all {len(rows)} resolvers return the same answer"
    return summary


def run(ctx: JobContext, params: Params) -> Summary:
    p = params
    argvs = build_argv(p)
    results: dict[str, Summary] = {}
    lock = threading.Lock()

    def one(resolver: str, argv: list[str]) -> None:
        try:
            r = ctx.run(argv, timeout=timeout(p), label=resolver)
            s = dig.parse(r.output)
            if r.timed_out:
                s.update(status="error", message="timed out")
        except Exception as exc:
            s = {"status": "error", "message": str(exc), "answer": []}
        with lock:
            results[resolver] = s
            ordered = {k: results[k] for k in p["resolvers"] if k in results}
            ctx.summary(
                {**compare(ordered), "pending": [k for k in p["resolvers"] if k not in results]}
            )

    threads = [
        threading.Thread(target=one, args=(res, argv), daemon=True)
        for res, argv in zip(p["resolvers"], argvs, strict=True)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ctx.check_cancelled()
    ordered = {k: results.get(k, {"status": "error", "answer": []}) for k in p["resolvers"]}
    return {**compare(ordered), "pending": [], "name": p["name"], "type": p["type"]}


TOOL = Tool(
    name="dnscompare",
    title="Resolver comparison",
    group="DNS",
    description="Send one query to several resolvers at once and compare the answers "
    "(useful to check DNS propagation).",
    validate=validate,
    run=run,
    timeout=lambda p: timeout(p) + 5,
    binaries=("dig",),
    target=lambda p: f"{p['name']} {p['type']}",
)
