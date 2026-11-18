# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""WCAG 2.1 AA contrast for every foreground/background pair the UI uses."""

import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parent.parent / "src/netpulse/static/css/app.css"


def tokens(theme: str) -> dict[str, str]:
    text = CSS.read_text()
    selector = ':root[data-theme="light"] {' if theme == "light" else ':root[data-theme="dark"] {'
    start = text.index(selector)
    block = text[start : text.index("}", start)]
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6});", block))


def luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT = 4.5  # normal text
UI = 3.0  # UI components, focus indicators, graphical objects (SC 1.4.11)

BACKGROUNDS = ["bg", "surface", "surface-2"]
PAIRS: list[tuple[str, str, float]] = [
    *[("text", b, TEXT) for b in [*BACKGROUNDS, "sidebar-bg", "sidebar-hover", "sidebar-active"]],
    *[("text-muted", b, TEXT) for b in [*BACKGROUNDS, "sidebar-bg", "sidebar-active"]],
    *[("link", b, TEXT) for b in BACKGROUNDS],
    *[("sidebar-heading", b, TEXT) for b in ("sidebar-bg", "sidebar-hover")],
    ("accent-text", "accent", TEXT),
    ("accent-text", "accent-hover", TEXT),
    ("surface", "err", TEXT),  # "Delete all" button
    *[(s, b, TEXT) for s in ("ok", "warn", "err", "info") for b in ("surface", "surface-2")],
    ("ok", "ok-bg", TEXT),
    ("warn", "warn-bg", TEXT),
    ("err", "err-bg", TEXT),
    ("info", "info-bg", TEXT),
    ("text", "ok-bg", TEXT),
    ("text", "warn-bg", TEXT),
    ("text", "err-bg", TEXT),
    ("text", "info-bg", TEXT),
    ("code-text", "code-bg", TEXT),
    *[("focus", b, UI) for b in [*BACKGROUNDS, "sidebar-bg", "code-bg"]],
    *[("border-strong", b, UI) for b in [*BACKGROUNDS, "sidebar-bg"]],
    ("accent", "surface", UI),
    ("chart-line", "surface", UI),
    ("chart-loss", "surface", UI),
    ("chart-axis", "surface", TEXT),
    *[(f"bar-{i}", "surface", UI) for i in range(1, 6)],
]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("fg,bg,minimum", PAIRS, ids=[f"{f}/{b}" for f, b, _ in PAIRS])
def test_contrast(theme, fg, bg, minimum):
    t = tokens(theme)
    r = ratio(t[fg], t[bg])
    assert r >= minimum, f"{theme}: --{fg} {t[fg]} on --{bg} {t[bg]} = {r:.2f} < {minimum}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_both_themes_define_same_tokens(theme):
    assert set(tokens(theme)) == set(tokens("light"))
