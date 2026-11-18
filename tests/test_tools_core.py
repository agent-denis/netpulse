# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""Phase 1 tools: argv building and parsing of captured real outputs."""

import pytest

from conftest import fixture
from netpulse import miniyaml
from netpulse.tools import dig, nslookup, ping, traceroute
from netpulse.validators import ValidationError

BAD_HOSTS = ["; rm -rf ~", "$(id)", "`id`", "--help", "-oProxyCommand=x", "a\nb", "a b", ""]


# ------------------------------------------------------------------ ping
def test_ping_argv_defaults():
    assert ping.build_argv({"host": "fedoraproject.org"}) == [
        "ping", "-n", "-O", "-c", "4", "-i", "1", "-s", "56", "-W", "2", "--", "fedoraproject.org",
    ]  # fmt: skip


def test_ping_argv_options_and_clamping():
    argv = ping.build_argv(
        {"host": "::1", "count": 500, "interval": 0.01, "size": 1400, "family": "6"}
    )
    assert argv[argv.index("-c") + 1] == "100"
    assert argv[argv.index("-i") + 1] == "0.2"
    assert argv[argv.index("-s") + 1] == "1400"
    assert "-6" in argv
    assert argv[-2:] == ["--", "::1"]


def test_ping_argv_idn_and_scope():
    assert ping.build_argv({"host": "bücher.de"})[-1] == "xn--bcher-kva.de"
    assert ping.build_argv({"host": "fe80::1%eth0"})[-1] == "fe80::1%eth0"


@pytest.mark.parametrize("bad", BAD_HOSTS)
def test_ping_rejects_bad_hosts(bad):
    with pytest.raises(ValidationError):
        ping.build_argv({"host": bad})


def test_ping_rejects_bad_options():
    with pytest.raises(ValidationError):
        ping.build_argv({"host": "a.org", "family": "4; id"})
    with pytest.raises(ValidationError):
        ping.build_argv({"host": "a.org", "count": "4 -f"})


def test_ping_parse_ipv4_success():
    s = ping.parse(fixture("ping_v4_internet.txt"))
    assert s["status"] == "ok"
    assert (s["transmitted"], s["received"], s["loss_pct"]) == (5, 5, 0.0)
    assert (s["min"], s["avg"], s["max"], s["mdev"]) == (17.445, 20.351, 24.670, 2.450)
    assert [p["rtt"] for p in s["points"]] == [24.7, 19.5, 17.4, 21.1, 19.1]
    assert s["address"] == "1.1.1.1"


def test_ping_parse_ipv6_success():
    s = ping.parse(fixture("ping_v6_localhost.txt"))
    assert s["status"] == "ok" and s["address"] == "::1"
    assert [p["seq"] for p in s["points"]] == [1, 2, 3, 4]
    assert s["points"][0]["from"] == "::1"


def test_ping_parse_partial_loss_and_icmp_error():
    s = ping.parse(fixture("ping_v4_hostname.txt"))
    assert s["status"] == "warning"
    assert s["received"] == 2 and s["errors"] == 1
    assert s["points"][0] == {"seq": 1, "rtt": None, "ttl": None}
    assert s["icmp_errors"][0]["message"].startswith("Frag needed")
    assert s["message"] == "33.3% packet loss"


def test_ping_parse_timeout():
    s = ping.parse(fixture("ping_v4_timeout.txt"))
    assert s["status"] == "error"
    assert s["loss_pct"] == 100.0
    assert [p["rtt"] for p in s["points"]] == [None, None, None, None]


@pytest.mark.parametrize("name", ["ping_unknown_host.txt", "ping_v6_internet.txt"])
def test_ping_parse_failures(name):
    s = ping.parse(fixture(name))
    assert s["status"] == "error" and s["message"]


def test_ping_live_partial_output():
    text = fixture("ping_v4_timeout.txt").splitlines()
    partial = ping.parse("\n".join(text[:3]))
    assert not partial["complete"]
    assert [p["rtt"] for p in partial["points"]] == [None, None]


# ------------------------------------------------------------------ traceroute
def test_traceroute_argv(monkeypatch):
    argv = traceroute.build_argv({"host": "1.1.1.1", "max_hops": 99, "probes": 2}, "traceroute")
    assert argv == ["traceroute", "-m", "64", "-q", "2", "-w", "3", "--", "1.1.1.1"]
    argv = traceroute.build_argv(
        {"host": "a.org", "mode": "icmp", "family": "4", "resolve": False}, "traceroute"
    )
    assert argv[:4] == ["traceroute", "-n", "-4", "-I"]
    assert "-T" in traceroute.build_argv({"host": "a.org", "mode": "tcp"}, "traceroute")


def test_tracepath_argv():
    argv = traceroute.build_argv({"host": "::1", "family": "6", "max_hops": 5}, "tracepath")
    assert argv == ["stdbuf", "-oL", "tracepath", "-m", "5", "-6", "--", "::1"]


def test_traceroute_backend_fallback(monkeypatch):
    monkeypatch.setattr(traceroute.detect, "which", lambda b: None if b == "traceroute" else "/x")
    assert traceroute.backend() == "tracepath"
    assert traceroute.build_argv({"host": "a.org"})[2] == "tracepath"


@pytest.mark.parametrize("bad", BAD_HOSTS)
def test_traceroute_rejects_bad_hosts(bad):
    with pytest.raises(ValidationError):
        traceroute.build_argv({"host": bad}, "traceroute")


def test_traceroute_parse_reached():
    s = traceroute.parse(fixture("traceroute_v4_internet.txt"))
    assert s["status"] == "ok" and s["reached"]
    assert s["hop_count"] == 14
    hop1 = s["hops"][0]
    assert hop1["ip"] == "192.168.202.1" and hop1["rtts"] == [1.376, 1.341, 1.315]
    assert s["hops"][2]["loss_pct"] == 100.0
    hop7 = s["hops"][6]
    assert [h["ip"] for h in hop7["hosts"]] == ["10.64.0.2", "10.64.0.6"]
    assert s["hops"][-1]["ip"] == "1.1.1.1"


def test_traceroute_parse_hostnames_and_mixed_probes():
    s = traceroute.parse(fixture("traceroute_v4_hostname.txt"))
    assert s["hops"][0]["hostname"] == "_gateway"
    assert s["hops"][0]["ip"] == "192.168.202.1"
    hop10 = s["hops"][9]
    assert hop10["lost"] == 2 and hop10["hostname"] == "core1.transit.example.net"
    assert not s["reached"] and s["status"] == "warning"


def test_traceroute_parse_ipv6_and_timeouts():
    assert traceroute.parse(fixture("traceroute_v6_localhost.txt"))["reached"]
    s = traceroute.parse(fixture("traceroute_v4_timeout.txt"))
    assert s["status"] == "warning" and s["hops"][-1]["loss_pct"] == 100.0


@pytest.mark.parametrize(
    "name",
    ["traceroute_unknown_host.txt", "traceroute_v6_internet.txt", "traceroute_tcp_noperm.txt"],
)
def test_traceroute_parse_errors(name):
    s = traceroute.parse(fixture(name))
    assert s["status"] == "error"


def test_traceroute_privilege_message():
    s = traceroute.parse(fixture("traceroute_tcp_noperm.txt"))
    assert "root" in s["message"]


def test_tracepath_parse():
    s = traceroute.parse(fixture("tracepath_v4_internet.txt"))
    assert s["backend"] == "tracepath"
    assert s["hops"][0]["rtts"] == [1.247, 1.245]
    assert s["pmtu"] == 1380
    assert "asymm 3" in s["hops"][3]["annotations"]
    s = traceroute.parse(fixture("tracepath_v6_localhost.txt"))
    assert s["reached"] and s["hops"][0]["hostname"] == "localhost"
    assert traceroute.parse(fixture("tracepath_unknown_host.txt"))["status"] == "error"
    assert not traceroute.parse(fixture("tracepath_v4_timeout.txt"))["reached"]


# ------------------------------------------------------------------ dig
def test_dig_argv():
    assert dig.build_argv({"name": "fedoraproject.org"}) == [
        "dig", "-r", "+yaml", "+timeout=5", "+tries=2", "-t", "A", "-q", "fedoraproject.org",
    ]  # fmt: skip
    argv = dig.build_argv(
        {
            "name": "_dmarc.example.com",
            "type": "TXT",
            "resolver": "9.9.9.9",
            "dnssec": True,
            "tcp": True,
        }
    )
    assert "@9.9.9.9" in argv and "+dnssec" in argv and "+tcp" in argv
    assert argv[-4:] == ["-t", "TXT", "-q", "_dmarc.example.com"]
    short = dig.build_argv({"name": "a.org", "short": True})
    assert "+yaml" not in short and "+short" in short


def test_dig_argv_custom_resolver_and_ptr():
    argv = dig.build_argv({"name": "a.org", "resolver": "custom", "custom": "dns.quad9.net"})
    assert "@dns.quad9.net" in argv
    argv = dig.build_argv({"name": "1.1.1.1", "type": "PTR"})
    assert argv[-1] == "1.1.1.1.in-addr.arpa."


@pytest.mark.parametrize(
    "params",
    [
        {"name": "$(id)"},
        {"name": "-x"},
        {"name": "a.org", "type": "AXFR"},
        {"name": "a.org", "type": "A +tcp"},
        {"name": "a.org", "resolver": "custom", "custom": "-p53"},
        {"name": "a.org", "resolver": "custom", "custom": "1.1.1.1 +tcp"},
        {"name": "a.org", "resolver": "4.4.4.4"},
        {"name": "a.org", "short": "maybe"},
    ],
)
def test_dig_rejects(params):
    with pytest.raises(ValidationError):
        dig.build_argv(params)


def test_dig_parse_answer_section():
    s = dig.parse(fixture("dig_yaml_a.txt"))
    assert s["status"] == "ok" and s["rcode"] == "NOERROR"
    assert s["answer_count"] == 8
    rec = s["answer"][0]
    assert rec == {
        "name": "fedoraproject.org.",
        "ttl": 4,
        "class": "IN",
        "type": "A",
        "data": "152.2.23.103",
    }
    assert s["flags"] == ["qr", "rd", "ra"]
    assert s["server"] == "127.0.0.53#53" and s["protocol"] == "UDP"


def test_dig_parse_record_types():
    assert dig.parse(fixture("dig_yaml_mx.txt"))["answer"][0]["data"].startswith(("10 ", "20 "))
    txt = dig.parse(fixture("dig_yaml_txt.txt"))["answer"]
    assert any(r["data"].startswith('"v=spf1') for r in txt)
    soa = dig.parse(fixture("dig_yaml_soa.txt"))["answer"][0]
    assert soa["type"] == "SOA" and "hostmaster" in soa["data"]
    assert dig.parse(fixture("dig_yaml_aaaa.txt"))["answer"][0]["type"] == "AAAA"
    assert dig.parse(fixture("dig_yaml_caa.txt"))["answer"][0]["type"] == "CAA"
    assert dig.parse(fixture("dig_yaml_srv.txt"))["answer"][0]["type"] == "SRV"
    ptr6 = dig.parse(fixture("dig_yaml_ptr_v6.txt"))["answer"][0]
    assert ptr6["data"] == "one.one.one.one."


def test_dig_parse_dnssec_and_tcp():
    s = dig.parse(fixture("dig_yaml_dnskey_dnssec.txt"))
    assert any(r["type"] == "RRSIG" for r in s["answer"])
    assert "do" in s["edns_flags"]
    assert dig.parse(fixture("dig_yaml_tcp.txt"))["protocol"] == "TCP"


def test_dig_parse_negative_and_errors():
    nx = dig.parse(fixture("dig_yaml_nxdomain.txt"))
    assert nx["status"] == "warning" and nx["rcode"] == "NXDOMAIN"
    sf = dig.parse(fixture("dig_yaml_servfail.txt"))
    assert sf["status"] == "error" and sf["rcode"] == "SERVFAIL"
    assert "DNSKEY Missing" in sf["ede"]
    to = dig.parse(fixture("dig_yaml_timeout.txt"))
    assert to["status"] == "error" and to["message"] == "no servers could be reached"


def test_dig_parse_trace_chain():
    s = dig.parse(fixture("dig_yaml_trace.txt"))
    assert len(s["chain"]) >= 3
    assert s["chain"][0]["kind"] == "RECURSIVE_RESPONSE"
    assert s["status"] == "ok" and s["answer"]


def test_dig_parse_short_and_text():
    s = dig.parse(fixture("dig_short_a.txt"))
    assert s["status"] == "ok" and len(s["short"]) == 8
    t = dig.parse(fixture("dig_text_a.txt"))
    assert t["rcode"] == "NOERROR" and t["answer_count"] == 8 and t["protocol"] == "UDP"


def test_miniyaml_subset():
    doc = miniyaml.loads(
        "- type: X\n  message: |\n    line one\n    line two\n- type: Y\n  list:\n    - 'it''s'\n"
        '    - "a\\tb"\n  empty:\n  n: 42\n  ts: !!timestamp 2026-01-01T00:00:00Z\n'
    )
    assert doc[0] == {"type": "X", "message": "line one\nline two\n"}
    assert doc[1]["list"] == ["it's", "a\tb"]
    assert doc[1]["empty"] is None and doc[1]["n"] == 42
    assert doc[1]["ts"] == "2026-01-01T00:00:00Z"


# ------------------------------------------------------------------ nslookup
def test_nslookup_argv():
    params = {"name": "fedoraproject.org", "type": "MX", "resolver": "8.8.8.8"}
    assert nslookup.build_argv(params) == [
        "nslookup", "-type=MX", "-timeout=5", "-retry=2", "fedoraproject.org", "8.8.8.8",
    ]  # fmt: skip
    assert nslookup.build_argv({"name": "1.1.1.1", "type": "PTR"})[-1] == "1.1.1.1"


@pytest.mark.parametrize(
    "params",
    [
        {"name": "-query=any"},
        {"name": "a.org", "type": "AXFR"},
        {"name": "a.org; id"},
        {"name": "a.org", "resolver": "custom", "custom": "-port=5353"},
    ],
)
def test_nslookup_rejects(params):
    with pytest.raises(ValidationError):
        nslookup.build_argv(params)


def test_nslookup_parse_records():
    a = nslookup.parse(fixture("nslookup_a.txt"))
    assert a["status"] == "ok" and a["answer_count"] == 8 and not a["authoritative"]
    assert a["server"] == "127.0.0.53#53"
    v6 = nslookup.parse(fixture("nslookup_aaaa_server.txt"))
    assert all(r["type"] == "AAAA" for r in v6["answer"]) and v6["server"] == "1.1.1.1#53"
    mx = nslookup.parse(fixture("nslookup_mx.txt"))["answer"]
    assert mx[0] == {
        "name": "fedoraproject.org",
        "type": "MX",
        "data": "10 us-smtp-inbound-1.mimecast.com.",
    }
    soa = nslookup.parse(fixture("nslookup_soa.txt"))["answer"][0]
    assert soa["type"] == "SOA" and soa["soa"]["serial"] == 2794942600
    assert nslookup.parse(fixture("nslookup_ptr.txt"))["answer"][0]["data"] == "one.one.one.one."
    assert nslookup.parse(fixture("nslookup_cname.txt"))["answer"][0]["type"] == "CNAME"
    assert nslookup.parse(fixture("nslookup_caa.txt"))["answer"][0]["type"] == "CAA"
    assert nslookup.parse(fixture("nslookup_srv.txt"))["answer"][0]["type"] == "SRV"
    assert len(nslookup.parse(fixture("nslookup_txt.txt"))["answer"]) == 6


def test_nslookup_parse_failures():
    nx = nslookup.parse(fixture("nslookup_nxdomain.txt"))
    assert nx["rcode"] == "NXDOMAIN" and nx["status"] == "warning"
    assert nslookup.parse(fixture("nslookup_servfail.txt"))["status"] == "error"
    to = nslookup.parse(fixture("nslookup_timeout.txt"))
    assert to["status"] == "error" and "timed out" in to["message"]
    assert nslookup.parse(fixture("nslookup_any.txt"))["rcode"] == "NOTIMP"
