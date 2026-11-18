# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Job management: run tools in the background and record their events.

Every external command runs with ``shell=False`` in its own session/process
group, so cancel/timeout/disconnect can kill the whole group with
``os.killpg``. Every child is ``wait()``-ed, so no zombies are left behind.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Defaults, overridable per manager.
MAX_CONCURRENT_JOBS = 8
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
KEEP_FINISHED_JOBS = 60
DISCONNECT_GRACE_S = 5.0
UNCLAIMED_GRACE_S = 20.0
KILL_WAIT_S = 1.5

SAFE_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"

FINAL_STATES = {"done", "failed", "cancelled", "timeout", "error"}


class JobLimitError(RuntimeError):
    """Too many jobs are running already."""


class ToolMissingError(RuntimeError):
    """The external binary is not installed."""


class JobCancelledError(Exception):
    """Raised inside a job function when it should stop."""


@dataclass
class ProcessResult:
    argv: list[str]
    returncode: int | None
    output: str
    timed_out: bool = False
    cancelled: bool = False
    truncated: bool = False


def child_env() -> dict[str, str]:
    """A small, predictable environment: C locale for parseable output."""
    env = {"PATH": SAFE_PATH, "LC_ALL": "C", "LANG": "C"}
    for key in ("HOME", "USER", "LOGNAME", "TZ"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def kill_process_group(proc: subprocess.Popen[str], wait_s: float = KILL_WAIT_S) -> None:
    """SIGTERM the process group, then SIGKILL if it doesn't exit in time. Always reaps."""
    if proc.poll() is None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=wait_s)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    else:
        # The leader is gone; make sure no stragglers of the group survive.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)


@dataclass
class Job:
    tool: str
    title: str
    params: dict[str, Any]
    id: str = field(default_factory=lambda: secrets.token_hex(8))
    status: str = "queued"
    message: str = ""
    exit_code: int | None = None
    started_at: float = field(default_factory=time.time)
    _t0: float = field(default_factory=time.monotonic)
    elapsed: float = 0.0
    summary: dict[str, Any] = field(default_factory=dict)
    argv_display: list[list[str]] = field(default_factory=list)
    output_bytes: int = 0
    truncated: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: int = 0
    cancel_reason: str = ""
    _output: list[str] = field(default_factory=list)
    _procs: set[subprocess.Popen[str]] = field(default_factory=set)
    _cond: threading.Condition = field(default_factory=threading.Condition)
    _cancel: threading.Event = field(default_factory=threading.Event)

    # ---------------------------------------------------------------- state
    @property
    def finished(self) -> bool:
        return self.status in FINAL_STATES

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def output(self) -> str:
        with self._cond:
            return "".join(self._output)

    def current_elapsed(self) -> float:
        return self.elapsed if self.finished else time.monotonic() - self._t0

    def push(self, etype: str, **data: Any) -> None:
        with self._cond:
            event = {"seq": len(self.events), "type": etype, **data}
            self.events.append(event)
            self._cond.notify_all()

    def events_since(self, seq: int, timeout: float) -> list[dict[str, Any]]:
        """Return events with index >= seq, waiting up to *timeout* for new ones."""
        with self._cond:
            if seq >= len(self.events) and not self.finished:
                self._cond.wait(timeout)
            return self.events[seq:]

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "title": self.title,
            "params": self.params,
            "status": self.status,
            "message": self.message,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "elapsed": round(self.current_elapsed(), 3),
            "summary": self.summary,
            "commands": self.argv_display,
            "truncated": self.truncated,
            "events": len(self.events),
        }

    def record(self, max_output: int = 64 * 1024) -> dict[str, Any]:
        """The history entry for this job."""
        out = self.output
        data = self.snapshot()
        data.pop("events", None)
        data["output"] = out if len(out) <= max_output else out[:max_output] + "\n[… truncated]\n"
        return data


class JobContext:
    """What a tool's ``run`` function gets to talk to the job."""

    def __init__(self, job: Job, manager: JobManager) -> None:
        self.job = job
        self.manager = manager

    @property
    def cancelled(self) -> bool:
        return self.job.cancelled

    def check_cancelled(self) -> None:
        if self.job.cancelled:
            raise JobCancelledError

    def output(self, text: str) -> None:
        job = self.job
        if job.truncated:
            return
        size = len(text.encode("utf-8", "replace"))
        if job.output_bytes + size > self.manager.max_output_bytes:
            job.truncated = True
            notice = (
                f"\n[NetPulse: output limit of {self.manager.max_output_bytes} bytes reached]\n"
            )
            with job._cond:
                job._output.append(notice)
            job.push("output", text=notice)
            self.manager.cancel(job.id, reason="output limit reached")
            return
        job.output_bytes += size
        with job._cond:
            job._output.append(text)
        job.push("output", text=text)

    def summary(self, data: dict[str, Any]) -> None:
        """Publish a (partial) parsed summary."""
        self.job.summary = data
        self.job.push("summary", data=data)

    def note(self, message: str) -> None:
        self.job.message = message
        self.job.push("status", status=self.job.status, message=message)

    def run(
        self,
        argv: list[str],
        *,
        timeout: float,
        on_line: Callable[[str], None] | None = None,
        echo: bool = True,
        label: str | None = None,
    ) -> ProcessResult:
        """Run one external command, streaming its output. Never uses a shell."""
        if not argv or not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
            raise TypeError("argv must be a non-empty list of strings")
        self.check_cancelled()
        exe = shutil.which(argv[0], path=SAFE_PATH)
        if exe is None:
            raise ToolMissingError(argv[0])
        self.job.argv_display.append(argv)
        if echo:
            self.output(
                f"$ {' '.join(argv)}\n" if label is None else f"$ [{label}] {' '.join(argv)}\n"
            )
        proc = subprocess.Popen(
            [exe, *argv[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            start_new_session=True,
            close_fds=True,
            env=child_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        timed_out = threading.Event()

        def on_timeout() -> None:
            timed_out.set()
            kill_process_group(proc)

        with self.job._cond:
            self.job._procs.add(proc)
        if self.job.cancelled:  # cancelled while we were starting it
            kill_process_group(proc)
        timer = threading.Timer(timeout, on_timeout)
        timer.daemon = True
        timer.start()
        lines: list[str] = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.append(line)
                if echo:
                    self.output(line if label is None else f"[{label}] {line}")
                if on_line is not None and not self.job.cancelled:
                    on_line(line)
            proc.wait()
        finally:
            timer.cancel()
            kill_process_group(proc)
            with self.job._cond:
                self.job._procs.discard(proc)
        return ProcessResult(
            argv=argv,
            returncode=proc.returncode,
            output="".join(lines),
            timed_out=timed_out.is_set(),
            cancelled=self.job.cancelled and not timed_out.is_set(),
            truncated=self.job.truncated,
        )


JobFunc = Callable[[JobContext, dict[str, Any]], dict[str, Any]]


class JobManager:
    def __init__(
        self,
        *,
        max_jobs: int = MAX_CONCURRENT_JOBS,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        on_finish: Callable[[Job], None] | None = None,
        disconnect_grace: float = DISCONNECT_GRACE_S,
        unclaimed_grace: float = UNCLAIMED_GRACE_S,
    ) -> None:
        self.max_jobs = max_jobs
        self.max_output_bytes = max_output_bytes
        self.on_finish = on_finish
        self.disconnect_grace = disconnect_grace
        self.unclaimed_grace = unclaimed_grace
        self._jobs: dict[str, Job] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self.closing = False

    # ---------------------------------------------------------------- queries
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def running(self) -> list[Job]:
        return [j for j in self.list() if not j.finished]

    # ---------------------------------------------------------------- control
    def submit(
        self, tool: str, title: str, params: dict[str, Any], func: JobFunc, timeout: float
    ) -> Job:
        """Start *func* in a thread. *timeout* is the hard limit for the whole job."""
        if self.closing:
            raise JobLimitError("NetPulse is shutting down")
        with self._lock:
            active = sum(1 for j in self._jobs.values() if not j.finished)
            if active >= self.max_jobs:
                raise JobLimitError(f"at most {self.max_jobs} jobs can run at the same time")
            job = Job(tool=tool, title=title, params=params)
            self._jobs[job.id] = job
            self._prune_locked()
        thread = threading.Thread(
            target=self._run, args=(job, func, timeout), name=f"job-{job.id}", daemon=True
        )
        self._threads[job.id] = thread
        thread.start()
        self._watch_subscribers(job, self.unclaimed_grace)
        return job

    def cancel(self, job_id: str, reason: str = "cancelled by user") -> bool:
        job = self.get(job_id)
        if job is None or job.finished:
            return False
        if not job._cancel.is_set():
            job.cancel_reason = reason
            job._cancel.set()
        with job._cond:
            procs = list(job._procs)
        for proc in procs:
            kill_process_group(proc)
        return True

    def subscribe(self, job: Job) -> None:
        with job._cond:
            job.subscribers += 1

    def unsubscribe(self, job: Job) -> None:
        with job._cond:
            job.subscribers -= 1
            remaining = job.subscribers
        if remaining <= 0 and not job.finished:
            self._watch_subscribers(job, self.disconnect_grace)

    def shutdown(self, timeout: float = 5.0) -> None:
        """Cancel every job and wait for its thread (and children) to finish."""
        self.closing = True
        for job in self.list():
            self.cancel(job.id, reason="NetPulse is shutting down")
        deadline = time.monotonic() + timeout
        for thread in list(self._threads.values()):
            thread.join(max(0.0, deadline - time.monotonic()))

    # ---------------------------------------------------------------- internals
    def _watch_subscribers(self, job: Job, grace: float) -> None:
        """Cancel *job* if nobody is listening to it after *grace* seconds."""

        def check() -> None:
            if not job.finished and job.subscribers <= 0:
                self.cancel(job.id, reason="client disconnected")

        timer = threading.Timer(grace, check)
        timer.daemon = True
        timer.start()

    def _prune_locked(self) -> None:
        finished = [j for j in self._jobs.values() if j.finished]
        for job in finished[:-KEEP_FINISHED_JOBS] if len(finished) > KEEP_FINISHED_JOBS else []:
            self._jobs.pop(job.id, None)
            self._threads.pop(job.id, None)

    def _run(self, job: Job, func: JobFunc, timeout: float) -> None:
        ctx = JobContext(job, self)
        job.status = "running"
        job.push("status", status="running", message="")
        deadline = threading.Timer(timeout, lambda: self.cancel(job.id, reason="timeout"))
        deadline.daemon = True
        deadline.start()
        status, message = "done", ""
        try:
            summary = func(ctx, job.params) or {}
            if summary:
                job.summary = summary
            if job.cancelled:
                status = "timeout" if job.cancel_reason == "timeout" else "cancelled"
                message = job.cancel_reason
            elif summary.get("status") == "error":
                status, message = "failed", str(summary.get("message", ""))
            else:
                message = str(summary.get("message", ""))
        except JobCancelledError:
            status = "timeout" if job.cancel_reason == "timeout" else "cancelled"
            message = job.cancel_reason
        except ToolMissingError as exc:
            status, message = "error", f"'{exc}' is not installed"
        except Exception as exc:  # report, never crash the server
            status, message = "error", f"internal error: {type(exc).__name__}: {exc}"
        finally:
            deadline.cancel()
            with job._cond:
                procs = list(job._procs)
            for proc in procs:
                kill_process_group(proc)
        if job.truncated and status == "cancelled":
            status, message = "done", "output limit reached; output was truncated"
        job.elapsed = time.monotonic() - job._t0
        job.exit_code = job.summary.get("exit_code") if isinstance(job.summary, dict) else None
        job.status = status
        job.message = message
        job.push(
            "end",
            status=status,
            message=message,
            exit_code=job.exit_code,
            elapsed=round(job.elapsed, 3),
            summary=job.summary,
        )
        if self.on_finish is not None:
            with contextlib.suppress(Exception):
                self.on_finish(job)
