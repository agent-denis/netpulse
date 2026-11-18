# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""mtr: per-hop loss and latency over several cycles (``mtr --json``)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from netpulse import validators as v
from netpulse.jobs import JobContext
from netpulse.tools.base import Params, Summary, Tool

FAMILIES = ("auto", "4", "6")
MODES = ("udp", "icmp", "tcp")


def validate(params: Params) -> Params:
    return {
        "host": v.host_or_ip(params.get("host"), "host"),
        "cycles": v.int_range(params.get("cycles"), 1, 100, "cycles", default=10),
        "max_hops": v.int_range(params.get("max_hops"), 1, 64, "max_hops", default=30),
        "family": v.choice(params.get("family"), FAMILIES, "family", default="auto"),
        "mode": v.choice(params.get("mode"), MODES, "mode", default="udp"),
        "resolve": v.boolean(params.get("resolve"), "resolve", default=True),
    }


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    argv = ["mtr", "--json", "-c", str(p["cycles"]), "-m", str(p["max_hops"])]
    if not p["resolve"]:
        argv.append("-n")
    argv += {"udp": ["-u"], "icmp": [], "tcp": ["-T", "-P", "443"]}[p["mode"]]
    if p["family"] != "auto":
        argv.append(f"-{p['family']}")
    return [*argv, "--", p["host"]]


def timeout(params: Params) -> float:
    # one cycle per second, plus resolving and the final wait
    return params["cycles"] * 1.2 + 30


def parse(output: str) -> Summary:
    start = output.find("{")
    errors = [ln.strip() for ln in output.splitlines() if ln.startswith("mtr:")]
    if start < 0:
        return {
            "status": "error",
            "message": "; ".join(errors) or "mtr produced no report",
            "hops": [],
        }
    try:
        data = json.loads(output[start : output.rfind("}") + 1])
    except ValueError:
        return {"status": "error", "message": "could not read mtr's JSON report", "hops": []}
    report = data.get("report", {})
    meta = report.get("mtr", {})
    hops: list[dict[str, Any]] = []
    for hub in report.get("hubs", []):
        host = hub.get("host")
        hops.append(
            {
                "hop": hub.get("count"),
                "host": None if host == "???" else host,
                "loss_pct": hub.get("Loss%"),
                "sent": hub.get("Snt"),
                "last": hub.get("Last"),
                "avg": hub.get("Avg"),
                "best": hub.get("Best"),
                "worst": hub.get("Wrst"),
                "stdev": hub.get("StDev"),
            }
        )
    last = hops[-1] if hops else None
    summary: Summary = {
        "target": meta.get("dst"),
        "cycles": meta.get("tests"),
        "hops": hops,
        "hop_count": len(hops),
        "final_loss_pct": last["loss_pct"] if last else None,
    }
    if not hops:
        summary["status"], summary["message"] = "error", "; ".join(errors) or "no hops reported"
    elif last and last["loss_pct"] == 100:
        summary["status"] = "warning"
        summary["message"] = (
            "the last hop did not answer (destination not reached, or it filters probes)"
        )
    elif last and last["loss_pct"]:
        summary["status"] = "warning"
        summary["message"] = f"{last['loss_pct']:g}% loss at the destination"
    else:
        summary["status"] = "ok"
        n = len(hops)
        summary["message"] = f"{n} hop{'s' if n != 1 else ''}, no loss at the destination"
    return summary


def run(ctx: JobContext, params: Params) -> Summary:
    # mtr --json writes its report only at the end; meanwhile we publish progress.
    p = params
    expected = p["cycles"] * 1.0 + 1
    done = threading.Event()
    t0 = time.monotonic()

    def progress() -> None:
        while not done.wait(0.5):
            elapsed = time.monotonic() - t0
            ctx.summary(
                {
                    "progress": min(0.99, elapsed / expected),
                    "message": f"running {p['cycles']} cycles (about {expected:.0f} s); "
                    "mtr prints its report when it finishes",
                    "hops": [],
                }
            )

    ticker = threading.Thread(target=progress, daemon=True)
    ticker.start()
    try:
        result = ctx.run(build_argv(p), timeout=timeout(p))
    finally:
        done.set()
        ticker.join()
    summary = parse(result.output)
    summary["exit_code"] = result.returncode
    if result.timed_out:
        summary["status"], summary["message"] = "error", "the command timed out"
    return summary


TOOL = Tool(
    name="mtr",
    title="MTR",
    group="Connectivity",
    description="Combined ping and traceroute: loss and latency for every hop over several cycles.",
    validate=validate,
    run=run,
    timeout=timeout,
    binaries=("mtr",),
    notes=(
        "mtr reports at the end of the run, so the hop table appears when all cycles are done.",
    ),
)
