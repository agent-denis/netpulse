# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""XDG paths and persistent settings."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from netpulse import validators as v

APP_DIR = "netpulse"

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "system",  # system | light | dark
    "history_enabled": True,
    "history_max": 500,
    "show_listening_sockets": False,
}


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var, "")
    path = Path(value) if value and Path(value).is_absolute() else Path.home() / fallback
    return path / APP_DIR


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def runtime_dir() -> Path:
    value = os.environ.get("XDG_RUNTIME_DIR", "")
    if value and Path(value).is_absolute() and Path(value).is_dir():
        return Path(value) / APP_DIR
    return Path(tempfile.gettempdir()) / f"{APP_DIR}-{os.getuid()}"


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        Path(tmp).chmod(mode)
        Path(tmp).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp).unlink()
        raise


def clean_settings(data: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge *data* onto *base* (or defaults), validating every known key."""
    out = dict(DEFAULT_SETTINGS if base is None else base)
    if "theme" in data:
        out["theme"] = v.choice(data["theme"], ("system", "light", "dark"), "theme")
    if "history_enabled" in data:
        out["history_enabled"] = v.boolean(data["history_enabled"], "history_enabled")
    if "history_max" in data:
        out["history_max"] = v.int_range(data["history_max"], 10, 10000, "history_max", default=500)
    if "show_listening_sockets" in data:
        out["show_listening_sockets"] = v.boolean(
            data["show_listening_sockets"], "show_listening_sockets"
        )
    return out


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "settings.json"
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(DEFAULT_SETTINGS)
        if not isinstance(raw, dict):
            return dict(DEFAULT_SETTINGS)
        try:
            return clean_settings(raw)
        except v.ValidationError:
            return dict(DEFAULT_SETTINGS)

    def get(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._data = clean_settings(changes, self._data)
            atomic_write(self.path, json.dumps(self._data, indent=2) + "\n")
            return dict(self._data)
