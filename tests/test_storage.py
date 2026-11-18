# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Settings, history and the single-instance lock."""

import json

import pytest

from netpulse import config
from netpulse.config import Settings
from netpulse.history import History
from netpulse.instance import InstanceLock
from netpulse.validators import ValidationError


def test_xdg_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    assert config.data_dir() == tmp_path / "d" / "netpulse"
    assert config.config_dir() == tmp_path / "c" / "netpulse"
    monkeypatch.setenv("XDG_DATA_HOME", "relative/path")  # must be ignored per XDG spec
    assert config.data_dir().is_absolute()


def test_settings_defaults_and_persist(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(path)
    assert s.get()["theme"] == "system"
    s.update({"theme": "light", "history_max": 99999})
    assert json.loads(path.read_text())["theme"] == "light"
    assert Settings(path).get()["history_max"] == 10000  # clamped
    assert (path.stat().st_mode & 0o777) == 0o600
    with pytest.raises(ValidationError):
        s.update({"theme": "<script>"})


def test_settings_ignore_corrupt_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert Settings(path).get()["theme"] == "system"
    path.write_text('{"theme": "evil"}')
    assert Settings(path).get()["theme"] == "system"


def entry(i, tool="ping"):
    return {
        "id": f"{i:016x}",
        "tool": tool,
        "title": f"Ping: host{i}",
        "params": {"host": f"host{i}"},
        "status": "done",
        "output": "x" * 10,
    }


def test_history_append_list_search(tmp_path):
    h = History(tmp_path / "h.jsonl")
    for i in range(5):
        h.append(entry(i, "ping" if i % 2 else "dig"))
    items = h.list()
    assert [e["id"] for e in items][:2] == [f"{4:016x}", f"{3:016x}"]
    assert "output" not in items[0]
    assert len(h.list("host3")) == 1
    assert len(h.list(tool="dig")) == 3
    assert h.get(f"{2:016x}")["output"] == "x" * 10
    h.clear()
    assert h.list() == []


def test_history_cap(tmp_path):
    h = History(tmp_path / "h.jsonl", max_entries=10)
    for i in range(40):
        h.append(entry(i))
    assert len(h._read_all()) <= 15
    h.set_max(10)
    ids = [e["id"] for e in h._read_all()]
    assert len(ids) == 10 and ids[-1] == f"{39:016x}"


def test_history_skips_corrupt_lines(tmp_path):
    path = tmp_path / "h.jsonl"
    path.write_text('{"id": "a"}\nnot json\n{"id": "b"}\n')
    assert [e["id"] for e in History(path).list()] == ["b", "a"]


def test_instance_lock(tmp_path):
    a = InstanceLock(tmp_path)
    b = InstanceLock(tmp_path)
    assert a.acquire()
    assert not b.acquire()
    a.publish(url="http://127.0.0.1:1/", token="t", mode="browser")
    assert b.read()["token"] == "t"
    assert (a.info_path.stat().st_mode & 0o777) == 0o600
    a.release()
    assert b.acquire()
    b.release()
