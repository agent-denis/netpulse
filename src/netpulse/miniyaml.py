# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""A tiny reader for the YAML subset that ``dig +yaml`` (BIND 9) produces.

Supported: block mappings and sequences (by indentation), plain / single- /
double-quoted scalars, ``!!tag`` prefixes, ``|`` literal blocks and
``- key: value`` items. That's all dig emits; the stdlib has no YAML parser
and NetPulse must not depend on PyYAML at runtime.
"""

from __future__ import annotations

import json
import re
from typing import Any

_KEY_RE = re.compile(r"^([^\s'\"#][^:]*?):(?:\s+(.*))?$")


class YamlError(ValueError):
    pass


def _lines(text: str) -> list[tuple[int, str]]:
    out = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or raw.strip() in ("---", "..."):
            out.append((-1, raw))  # blank: kept for literal blocks
            continue
        out.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    return out


def scalar(text: str) -> Any:
    text = text.strip()
    if text.startswith("!!"):
        text = text.split(None, 1)[1] if " " in text else ""
    if not text:
        return None
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        try:
            return json.loads(text)
        except ValueError:
            return text[1:-1]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


class _Parser:
    def __init__(self, text: str) -> None:
        self.lines = _lines(text)
        self.i = 0

    def _skip_blank(self) -> None:
        while self.i < len(self.lines) and self.lines[self.i][0] < 0:
            self.i += 1

    def _peek(self) -> tuple[int, str] | None:
        self._skip_blank()
        return self.lines[self.i] if self.i < len(self.lines) else None

    def block(self, indent: int) -> Any:
        nxt = self._peek()
        if nxt is None or nxt[0] < indent:
            return None
        if nxt[1] == "-" or nxt[1].startswith("- "):
            return self.seq(nxt[0])
        return self.map(nxt[0])

    def literal(self, parent_indent: int) -> str:
        collected: list[str] = []
        block_indent: int | None = None
        while self.i < len(self.lines):
            ind, _raw = self.lines[self.i]
            if ind < 0:
                collected.append("")
                self.i += 1
                continue
            if ind <= parent_indent:
                break
            if block_indent is None:
                block_indent = ind
            original = self.lines[self.i][1]
            collected.append(" " * (ind - block_indent) + original)
            self.i += 1
        while collected and collected[-1] == "":
            collected.pop()
        return "\n".join(collected) + "\n" if collected else ""

    def value(self, rest: str | None, indent: int) -> Any:
        if rest is None or rest == "":
            nxt = self._peek()
            if nxt is not None and (
                nxt[0] > indent or (nxt[0] == indent and (nxt[1] == "-" or nxt[1].startswith("- ")))
            ):
                return self.block(nxt[0])
            return None
        if rest in ("|", "|-", "|+", ">", ">-"):
            return self.literal(indent)
        return scalar(rest)

    def map(self, indent: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        while True:
            nxt = self._peek()
            if nxt is None or nxt[0] != indent or nxt[1].startswith("- ") or nxt[1] == "-":
                return out
            m = _KEY_RE.match(nxt[1])
            if not m:
                raise YamlError(f"line {self.i + 1}: expected 'key: value'")
            self.i += 1
            key, rest = m.group(1), m.group(2)
            out[key] = self.value(rest, indent)

    def seq(self, indent: int) -> list[Any]:
        out: list[Any] = []
        while True:
            nxt = self._peek()
            if nxt is None or nxt[0] != indent or not (nxt[1] == "-" or nxt[1].startswith("- ")):
                return out
            content = nxt[1][1:].strip()
            if not content:
                self.i += 1
                out.append(self.block(indent + 1))
            elif _KEY_RE.match(content) and not content.startswith(("'", '"')):
                # "- key: value" starts a mapping indented by 2.
                self.lines[self.i] = (indent + 2, content)
                out.append(self.map(indent + 2))
            else:
                self.i += 1
                out.append(scalar(content))


def loads(text: str) -> Any:
    parser = _Parser(text)
    result = parser.block(0)
    if parser._peek() is not None:
        raise YamlError(f"line {parser.i + 1}: unexpected content")
    return result
