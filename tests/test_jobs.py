# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""Job runner: streaming, cancel, timeout, output cap, process-group cleanup.

These tests use ``sh -c`` *as a test fixture* to spawn grandchildren; the
application itself never runs a shell.
"""

import os
import time

import pytest

from netpulse.jobs import JobContext, JobLimitError, JobManager


def wait_for(cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); check /proc state.
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def spawner(script: str, timeout: float = 30):
    """A job func running a shell script that writes child PIDs to its output."""

    def run(ctx: JobContext, params):
        r = ctx.run(["sh", "-c", script], timeout=timeout)
        return {"exit_code": r.returncode, "timed_out": r.timed_out, "cancelled": r.cancelled}

    return run


def child_pids(job):
    lines = [ln for ln in job.output.splitlines() if not ln.startswith("$ ")]
    return [int(x) for ln in lines for x in ln.split() if x.isdigit()]


def test_streams_output_and_finishes():
    mgr = JobManager()
    job = mgr.submit("t", "t", {}, spawner("echo one; echo two"), timeout=10)
    mgr.subscribe(job)
    assert wait_for(lambda: job.finished)
    assert job.status == "done"
    assert job.exit_code == 0
    assert "one\ntwo\n" in job.output
    types = [e["type"] for e in job.events]
    assert types[0] == "status" and types[-1] == "end"
    assert [e["seq"] for e in job.events] == list(range(len(job.events)))


def test_cancel_kills_whole_process_group():
    mgr = JobManager()
    script = "sleep 300 & echo $!; sleep 301 & echo $!; echo $$; wait"
    job = mgr.submit("t", "t", {}, spawner(script), timeout=60)
    mgr.subscribe(job)
    assert wait_for(lambda: len(child_pids(job)) == 3)
    pids = child_pids(job)
    assert all(pid_alive(p) for p in pids)
    assert mgr.cancel(job.id)
    assert wait_for(lambda: job.finished)
    assert job.status == "cancelled"
    assert wait_for(lambda: not any(pid_alive(p) for p in pids), 5)


def test_timeout_kills_process():
    mgr = JobManager()
    job = mgr.submit("t", "t", {}, spawner("echo $$; sleep 300", timeout=0.5), timeout=60)
    mgr.subscribe(job)
    assert wait_for(lambda: job.finished)
    assert job.summary["timed_out"] is True
    assert not pid_alive(child_pids(job)[0])


def test_job_level_timeout():
    mgr = JobManager()
    job = mgr.submit("t", "t", {}, spawner("echo $$; sleep 300", timeout=60), timeout=0.5)
    mgr.subscribe(job)
    assert wait_for(lambda: job.finished)
    assert job.status == "timeout"
    assert not pid_alive(child_pids(job)[0])


def test_term_ignoring_child_gets_sigkill():
    mgr = JobManager()
    script = "trap '' TERM; echo $$; while true; do sleep 0.1; done"
    job = mgr.submit("t", "t", {}, spawner(script), timeout=60)
    mgr.subscribe(job)
    assert wait_for(lambda: child_pids(job))
    mgr.cancel(job.id)
    assert wait_for(lambda: job.finished)
    assert wait_for(lambda: not pid_alive(child_pids(job)[0]), 5)


def test_disconnect_cancels_job():
    mgr = JobManager(disconnect_grace=0.2)
    job = mgr.submit("t", "t", {}, spawner("echo $$; sleep 300"), timeout=60)
    mgr.subscribe(job)
    assert wait_for(lambda: child_pids(job))
    mgr.unsubscribe(job)
    assert wait_for(lambda: job.finished)
    assert job.status == "cancelled"
    assert job.message == "client disconnected"
    assert not pid_alive(child_pids(job)[0])


def test_unclaimed_job_is_cancelled():
    mgr = JobManager(unclaimed_grace=0.2)
    job = mgr.submit("t", "t", {}, spawner("sleep 300"), timeout=60)
    assert wait_for(lambda: job.finished)
    assert job.message == "client disconnected"


def test_output_cap():
    mgr = JobManager(max_output_bytes=10_000)
    job = mgr.submit("t", "t", {}, spawner("yes 'line of output'"), timeout=30)
    mgr.subscribe(job)
    assert wait_for(lambda: job.finished)
    assert job.truncated
    assert job.status == "done"
    assert len(job.output) < 11_000


def test_concurrency_cap():
    mgr = JobManager(max_jobs=2)
    jobs = [mgr.submit("t", "t", {}, spawner("sleep 300"), timeout=60) for _ in range(2)]
    with pytest.raises(JobLimitError):
        mgr.submit("t", "t", {}, spawner("sleep 300"), timeout=60)
    mgr.shutdown()
    assert all(j.finished for j in jobs)


def test_shutdown_leaves_no_processes():
    mgr = JobManager()
    jobs = [mgr.submit("t", "t", {}, spawner("echo $$; sleep 300"), timeout=60) for _ in range(3)]
    for j in jobs:
        mgr.subscribe(j)
    assert wait_for(lambda: all(child_pids(j) for j in jobs))
    pids = [p for j in jobs for p in child_pids(j)]
    mgr.shutdown()
    assert all(j.finished for j in jobs)
    assert not any(pid_alive(p) for p in pids)
    with pytest.raises(JobLimitError):
        mgr.submit("t", "t", {}, spawner("true"), timeout=5)


def test_missing_tool_is_reported():
    def run(ctx, params):
        ctx.run(["netpulse-no-such-binary"], timeout=5)
        return {}

    mgr = JobManager()
    job = mgr.submit("t", "t", {}, run, timeout=5)
    assert wait_for(lambda: job.finished)
    assert job.status == "error"
    assert "not installed" in job.message


def test_exception_in_tool_is_reported():
    def run(ctx, params):
        raise RuntimeError("boom")

    mgr = JobManager()
    job = mgr.submit("t", "t", {}, run, timeout=5)
    assert wait_for(lambda: job.finished)
    assert job.status == "error" and "boom" in job.message


def test_run_rejects_string_argv():
    def run(ctx, params):
        ctx.run("echo hi", timeout=5)  # type: ignore[arg-type]
        return {}

    mgr = JobManager()
    job = mgr.submit("t", "t", {}, run, timeout=5)
    assert wait_for(lambda: job.finished)
    assert job.status == "error" and "TypeError" in job.message


def test_child_environment_is_minimal(monkeypatch):
    monkeypatch.setenv("NETPULSE_SECRET", "x")
    mgr = JobManager()
    job = mgr.submit("t", "t", {}, spawner("env"), timeout=10)
    mgr.subscribe(job)
    assert wait_for(lambda: job.finished)
    assert "NETPULSE_SECRET" not in job.output
    assert "LC_ALL=C" in job.output
