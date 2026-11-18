# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>

import hashlib
import re

import check_headers
import netpulse

# sha256 of https://www.gnu.org/licenses/gpl-3.0.txt
GPL3_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def test_every_source_file_has_spdx_header():
    files = check_headers.source_files()
    assert files, "no source files found"
    bad = [str(p) for p in files if check_headers.missing_header(p)]
    assert bad == []


def test_license_is_unmodified_gpl3():
    data = (check_headers.ROOT / "LICENSE").read_bytes()
    assert hashlib.sha256(data).hexdigest() == GPL3_SHA256


def test_spec_version_matches_package():
    spec = check_headers.ROOT / "packaging" / "netpulse.spec"
    if not spec.exists():
        return
    m = re.search(r"^Version:\s*(\S+)", spec.read_text(), re.M)
    assert m and m.group(1) == netpulse.__version__


def test_packaging_metadata_is_consistent():
    root = check_headers.ROOT
    app_id = netpulse.APP_ID
    desktop = root / "data" / f"{app_id}.desktop"
    metainfo = root / "data" / f"{app_id}.metainfo.xml"
    assert desktop.is_file() and metainfo.is_file()
    assert f"Icon={app_id}\n" in desktop.read_text()
    meta = metainfo.read_text()
    assert f"<id>{app_id}</id>" in meta
    assert f'<release version="{netpulse.__version__}"' in meta
    assert f"netpulse {netpulse.__version__}" in (root / "data" / "netpulse.1").read_text()
    assert f"## [{netpulse.__version__}]" in (root / "CHANGELOG.md").read_text()
    spec = (root / "packaging" / "netpulse.spec").read_text()
    assert f"%global app_id {app_id}" in spec
    # the hicolor icon and the one the web UI uses are the same file
    hicolor = root / "data/icons/hicolor/scalable/apps" / f"{app_id}.svg"
    web = root / "src/netpulse/static/icons/netpulse.svg"
    assert hicolor.read_bytes() == web.read_bytes()
    assert (root / "data/icons/hicolor/symbolic/apps" / f"{app_id}-symbolic.svg").is_file()
