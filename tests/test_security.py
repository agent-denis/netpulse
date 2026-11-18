# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis

from netpulse import security


def test_token_is_random_and_long():
    tokens = {security.new_token() for _ in range(20)}
    assert len(tokens) == 20
    assert all(len(t) >= 40 for t in tokens)


def test_check_token():
    t = security.new_token()
    assert security.check_token(t, t)
    assert not security.check_token(t, t[:-1])
    assert not security.check_token(t, "")
    assert not security.check_token(t, None)
    assert not security.check_token("", "")


def test_check_host():
    assert security.check_host("127.0.0.1:8000", "127.0.0.1", 8000)
    assert security.check_host("localhost:8000", "127.0.0.1", 8000)
    assert security.check_host("LOCALHOST:8000", "127.0.0.1", 8000)
    assert security.check_host("[::1]:8000", "::1", 8000)
    for bad in (
        None,
        "",
        "evil.com",
        "evil.com:8000",
        "127.0.0.1:8001",
        "127.0.0.1",
        "localhost",
        "127.0.0.1.nip.io:8000",
        "attacker.localhost:8000",
    ):
        assert not security.check_host(bad, "127.0.0.1", 8000), bad


def test_check_origin():
    assert security.check_origin(None, "127.0.0.1", 8000)
    assert security.check_origin("http://127.0.0.1:8000", "127.0.0.1", 8000)
    assert security.check_origin("http://localhost:8000", "127.0.0.1", 8000)
    for bad in (
        "null",
        "http://evil.com",
        "https://127.0.0.1:8000",
        "http://127.0.0.1:8001",
        "http://localhost.evil.com:8000",
        "",
    ):
        assert not security.check_origin(bad, "127.0.0.1", 8000), bad


def test_is_loopback():
    assert security.is_loopback("127.0.0.1")
    assert security.is_loopback("127.5.5.5")
    assert security.is_loopback("::1")
    for bad in ("0.0.0.0", "::", "192.168.1.1", "localhost", "", "8.8.8.8"):
        assert not security.is_loopback(bad)


def test_csp_is_strict():
    csp = security.CSP
    assert "default-src 'none'" in csp
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert "frame-ancestors 'none'" in csp
