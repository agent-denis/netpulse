# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Single-instance handling via a lock file in ``$XDG_RUNTIME_DIR/netpulse``."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import IO, Any

from netpulse import security
from netpulse.config import atomic_write, runtime_dir


class InstanceLock:
    def __init__(self, directory: Path | None = None) -> None:
        self.dir = directory or runtime_dir()
        self.lock_path = self.dir / "instance.lock"
        self.info_path = self.dir / "instance.json"
        self._fh: IO[str] | None = None

    def acquire(self) -> bool:
        """True if we are the only instance (lock is held until release/exit)."""
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.dir.chmod(0o700)
        fh = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def publish(self, *, url: str, token: str, mode: str) -> None:
        info = {"pid": os.getpid(), "url": url, "token": token, "mode": mode}
        atomic_write(self.info_path, json.dumps(info), mode=0o600)

    def read(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def release(self) -> None:
        if self._fh is not None:
            with contextlib.suppress(OSError):
                self.info_path.unlink()
            with contextlib.suppress(OSError):
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None


def ask_running_instance(info: dict[str, Any], timeout: float = 3.0) -> dict[str, Any] | None:
    """Ask the running instance to raise its window. Returns its reply or None."""
    url = str(info.get("url", ""))
    token = str(info.get("token", ""))
    if not url.startswith(("http://127.", "http://[::1]")):
        return None
    req = urllib.request.Request(  # noqa: S310 (checked: loopback http only)
        url.rstrip("/") + "/api/present",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", security.TOKEN_HEADER: token},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (loopback only)
            return json.loads(resp.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError):
        return None
