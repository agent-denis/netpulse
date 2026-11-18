# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Run history stored as JSON Lines in ``$XDG_DATA_HOME/netpulse/history.jsonl``."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from netpulse.config import atomic_write, data_dir


class History:
    def __init__(self, path: Path | None = None, max_entries: int = 500) -> None:
        self.path = path or data_dir() / "history.jsonl"
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._count: int | None = None

    def _read_all(self) -> list[dict[str, Any]]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue  # skip a corrupt line rather than losing everything
            if isinstance(item, dict) and "id" in item:
                entries.append(item)
        return entries

    def _write_all(self, entries: list[dict[str, Any]]) -> None:
        atomic_write(
            self.path, "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries)
        )

    def append(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            self.path.chmod(0o600)
            if self._count is None:
                self._count = len(self._read_all())
            else:
                self._count += 1
            # Trim with a little slack so we don't rewrite the file on every run.
            if self._count > self.max_entries + max(5, self.max_entries // 20):
                entries = self._read_all()[-self.max_entries :]
                self._write_all(entries)
                self._count = len(entries)

    def list(self, query: str = "", limit: int = 200, tool: str = "") -> list[dict[str, Any]]:
        """Newest first, without the bulky raw output."""
        query = query.strip().lower()
        with self._lock:
            entries = self._read_all()
        out = []
        for entry in reversed(entries):
            if tool and entry.get("tool") != tool:
                continue
            if query:
                hay = " ".join(
                    [
                        str(entry.get("tool", "")),
                        str(entry.get("title", "")),
                        json.dumps(entry.get("params", {})),
                        str(entry.get("status", "")),
                    ]
                ).lower()
                if query not in hay:
                    continue
            item = {k: val for k, val in entry.items() if k != "output"}
            out.append(item)
            if len(out) >= limit:
                break
        return out

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock:
            for entry in self._read_all():
                if entry.get("id") == entry_id:
                    return entry
        return None

    def clear(self) -> None:
        with self._lock:
            self._write_all([])
            self._count = 0

    def set_max(self, max_entries: int) -> None:
        with self._lock:
            self.max_entries = max_entries
            entries = self._read_all()
            if len(entries) > max_entries:
                entries = entries[-max_entries:]
                self._write_all(entries)
            self._count = len(entries)
