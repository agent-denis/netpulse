# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""Static checks on the frontend: no HTML injection sinks, CSP-compatible markup."""

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "src/netpulse/static"
JS = sorted(STATIC.rglob("*.js"))
HTML = sorted(STATIC.rglob("*.html"))

FORBIDDEN_JS = [
    r"\.innerHTML\b",
    r"\.outerHTML\b",
    r"insertAdjacentHTML",
    r"document\.write",
    r"\beval\s*\(",
    r"new\s+Function\s*\(",
    r"setAttribute\(\s*[\"']style[\"']",
    r"setAttribute\(\s*[\"']on",
    r"https?://(?!www\.w3\.org/2000/svg)",  # no remote resources
]


@pytest.mark.parametrize("path", JS, ids=lambda p: p.name)
def test_js_has_no_html_sinks_or_remote_urls(path):
    text = path.read_text()
    for pattern in FORBIDDEN_JS:
        assert not re.search(pattern, text), f"{path.name}: forbidden pattern {pattern}"


@pytest.mark.parametrize("path", HTML, ids=lambda p: p.name)
def test_html_is_csp_clean(path):
    text = path.read_text()
    # every <script> must have a src (no inline code)
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", text, re.S):
        assert "src=" in m.group(1) and not m.group(2).strip(), "inline script"
    assert "<style" not in text, "inline <style>"
    assert not re.search(r"\sstyle\s*=", text), "style attribute"
    assert not re.search(r"\son[a-z]+\s*=", text), "inline event handler"
    assert not re.search(r"(src|href)=\"(https?:)?//", text), "remote resource"


def test_every_referenced_asset_exists():
    html = (STATIC / "index.html").read_text()
    for ref in re.findall(r"(?:src|href)=\"([^\"#:]+)\"", html):
        assert (STATIC / ref).is_file(), ref


def test_js_imports_resolve():
    for path in JS:
        for ref in re.findall(r"from\s+\"(\.[^\"]+)\"", path.read_text()):
            assert (path.parent / ref).resolve().is_file(), f"{path.name} imports missing {ref}"


def test_frontend_module_for_every_backend_tool():
    from netpulse import tools

    for name in tools.load_all():
        assert (STATIC / "js/tools" / f"{name}.js").is_file(), f"no UI module for {name}"


def test_theme_init_is_classic_sync_script():
    html = (STATIC / "index.html").read_text()
    tag = re.search(r"<script[^>]*theme-init\.js[^>]*>", html).group(0)
    assert "defer" not in tag and "async" not in tag and "module" not in tag
    # it must come before the stylesheet so the first paint is themed
    assert html.index("theme-init.js") < html.index("app.css")
