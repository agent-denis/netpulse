# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Phase 2 tools: argv building and parsing of captured real outputs."""

import socket
import time
from datetime import UTC, datetime

import pytest

from conftest import fixture
from netpulse.jobs import JobManager
from netpulse.tools import (
    cidr,
    diagnose,
    dnscompare,
    host,
    httpcheck,
    localinfo,
    mtr,
    portcheck,
    rdns,
    tlscert,
    whois,
)
from netpulse.validators import ValidationError

INJECTIONS = ["; rm -rf ~", "$(id)", "`id`", "--help", "-oProxyCommand=x", "a\nb", "a b", ""]


# ------------------------------------------------------------------ reverse DNS
def test_rdns_argv():
    assert rdns.build_argv({"address": "1.1.1.1"})[-2:] == ["-x", "1.1.1.1"]
    argv = rdns.build_argv({"address": "2606:4700:4700::1111", "resolver": "9.9.9.9"})
    assert "@9.9.9.9" in argv and argv[-1] == "2606:4700:4700::1111"


@pytest.mark.parametrize("bad", [*INJECTIONS, "fedoraproject.org", "1.1.1.1/24"])
def test_rdns_rejects(bad):
    with pytest.raises(ValidationError):
        rdns.build_argv({"address": bad})


def test_rdns_parse():
    s = rdns.parse(fixture("dig_yaml_ptr_v4.txt"))
    assert s["names"] == ["one.one.one.one."] and s["status"] == "ok"
    assert s["reverse_name"] == "1.1.1.1.in-addr.arpa."
    assert rdns.parse(fixture("dig_yaml_ptr_v6.txt"))["names"] == ["one.one.one.one."]
    nx = rdns.parse(fixture("dig_yaml_ptr_nxdomain.txt"))
    assert nx["status"] == "warning" and nx["names"] == []


# ------------------------------------------------------------------ host
def test_host_argv():
    assert host.build_argv({"name": "fedoraproject.org"}) == [
        "host", "-W", "5", "--", "fedoraproject.org",
    ]  # fmt: skip
    argv = host.build_argv({"name": "fedoraproject.org", "type": "MX", "resolver": "1.1.1.1"})
    assert argv == ["host", "-W", "5", "-t", "MX", "--", "fedoraproject.org", "1.1.1.1"]


@pytest.mark.parametrize("bad", INJECTIONS)
def test_host_rejects(bad):
    with pytest.raises(ValidationError):
        host.build_argv({"name": bad})


def test_host_parse():
    s = host.parse(fixture("host_default.txt"))
    types = {r["type"] for r in s["records"]}
    assert types == {"A", "AAAA", "MX"}
    cname = host.parse(fixture("host_cname.txt"))["records"][0]
    assert cname == {
        "name": "www.fedoraproject.org", "type": "CNAME", "data": "wildcard.fedoraproject.org.",
    }  # fmt: skip
    assert host.parse(fixture("host_ptr.txt"))["records"][0]["data"] == "one.one.one.one."
    assert host.parse(fixture("host_soa.txt"))["records"][0]["type"] == "SOA"
    assert host.parse(fixture("host_caa.txt"))["records"][0]["type"] == "CAA"
    assert host.parse(fixture("host_txt.txt"))["records"][0]["type"] == "TXT"
    ns = host.parse(fixture("host_ns_server.txt"))
    assert ns["server"] == "1.1.1.1#53" and len(ns["records"]) == 4
    assert host.parse(fixture("host_nxdomain.txt"))["rcode"] == "NXDOMAIN"
    assert host.parse(fixture("host_servfail.txt"))["status"] == "error"
    assert host.parse(fixture("host_timeout.txt"))["status"] == "error"
    assert host.parse(fixture("host_localhost.txt"))["records"][1]["data"] == "::1"


# ------------------------------------------------------------------ whois
def test_whois_argv():
    assert whois.build_argv({"query": "fedoraproject.org"}) == [
        "whois",
        "-H",
        "--",
        "fedoraproject.org",
    ]
    assert whois.build_argv({"query": "8.8.8.8"})[-1] == "8.8.8.8"
    assert whois.build_argv({"query": "192.0.2.10/24"})[-1] == "192.0.2.0/24"
    assert whois.build_argv({"query": "bücher.de"})[-1] == "xn--bcher-kva.de"


@pytest.mark.parametrize("bad", [*INJECTIONS, "-h whois.evil.com x.org"])
def test_whois_rejects(bad):
    with pytest.raises(ValidationError):
        whois.build_argv({"query": bad})


NOW = datetime(2026, 11, 18, tzinfo=UTC)


def test_whois_parse_domains():
    org = whois.parse(fixture("whois_domain_org.txt"), NOW)
    assert org["registrar"] == "Nom-iq Ltd. dba COM LAUDE"
    assert org["created_date"] == "2003-09-24" and org["expires_date"] == "2027-09-24"
    assert org["name_servers"] == [
        "ns01.fedoraproject.org", "ns02.fedoraproject.org", "ns05.fedoraproject.org",
        "ns03.fedoraproject.org",
    ]  # fmt: skip
    assert org["abuse"] == "abuse@comlaude.com"
    assert org["days_to_expiry"] == 310 and org["status"] == "ok"
    uk = whois.parse(fixture("whois_domain_uk.txt"), NOW)
    assert uk["registrar"].startswith("British Broadcasting Corporation")
    assert uk["expires_date"] == "2034-12-13" and len(uk["name_servers"]) == 8
    de = whois.parse(fixture("whois_domain_de.txt"), NOW)
    assert de["name_servers"][0] == "ns1.denic.de"
    com = whois.parse(fixture("whois_domain_com.txt"), NOW)
    assert com["created_date"] == "1995-08-14"


def test_whois_parse_networks():
    arin = whois.parse(fixture("whois_ip_arin.txt"), NOW)
    assert (arin["netname"], arin["org"], arin["abuse"]) == (
        "GOGL", "Google LLC (GOGL)", "network-abuse@google.com",
    )  # fmt: skip
    apnic = whois.parse(fixture("whois_ip_apnic.txt"), NOW)
    assert apnic["netname"] == "APNIC-LABS" and apnic["abuse"] == "helpdesk@apnic.net"
    ripe = whois.parse(fixture("whois_ip_ripe.txt"), NOW)
    assert ripe["network"] == "193.0.0.0 - 193.0.7.255" and ripe["country"] == "NL"
    v6 = whois.parse(fixture("whois_ipv6_ripe.txt"), NOW)
    assert v6["network"] == "2a05:d010::/28" and v6["abuse"] == "trustandsafety@support.aws.com"


def test_whois_parse_nomatch_and_expiry_warning():
    assert whois.parse(fixture("whois_nomatch.txt"), NOW)["status"] == "warning"
    soon = whois.parse(fixture("whois_domain_org.txt"), datetime(2027, 9, 10, tzinfo=UTC))
    assert soon["status"] == "warning" and soon["days_to_expiry"] == 14


# ------------------------------------------------------------------ mtr
def test_mtr_argv():
    assert mtr.build_argv({"host": "1.1.1.1"}) == [
        "mtr", "--json", "-c", "10", "-m", "30", "-u", "--", "1.1.1.1",
    ]  # fmt: skip
    p = {"host": "::1", "cycles": 500, "family": "6", "resolve": False, "mode": "icmp"}
    assert mtr.build_argv(p) == ["mtr", "--json", "-c", "100", "-m", "30", "-n", "-6", "--", "::1"]
    assert mtr.build_argv({"host": "a.org", "mode": "tcp"})[-5:-2] == ["-T", "-P", "443"]


@pytest.mark.parametrize("bad", INJECTIONS)
def test_mtr_rejects(bad):
    with pytest.raises(ValidationError):
        mtr.build_argv({"host": bad})


def test_mtr_parse():
    s = mtr.parse(fixture("mtr_v4_localhost.json"))
    assert s["status"] == "ok" and s["hops"][0]["host"] == "localhost"
    s = mtr.parse(fixture("mtr_v4_internet.json"))
    assert s["hops"][0]["host"] == "192.168.202.1" and s["hops"][0]["loss_pct"] == 0.0
    assert s["hops"][1]["host"] is None and s["hops"][1]["loss_pct"] == 100.0
    assert mtr.parse(fixture("mtr_v6_localhost.json"))["hops"][0]["loss_pct"] == 0.0
    udp = mtr.parse(fixture("mtr_v4_udp_internet.json"))
    assert udp["hops"][-1]["host"] == "1.1.1.1" and udp["status"] == "ok"
    assert mtr.parse(fixture("mtr_v4_tcp.json"))["hops"][0]["host"] == "192.168.202.1"
    assert mtr.parse(fixture("mtr_v4_timeout.json"))["status"] == "warning"
    for name in ("mtr_unknown_host.json", "mtr_v6_internet.json"):
        assert mtr.parse(fixture(name))["status"] == "error"


# ------------------------------------------------------------------ resolver comparison
def test_dnscompare_validate_and_argv():
    p = dnscompare.validate({"name": "fedoraproject.org", "custom": "192.168.1.1, dns.quad9.net"})
    assert p["resolvers"] == ["1.1.1.1", "8.8.8.8", "9.9.9.9", "192.168.1.1", "dns.quad9.net"]
    assert dnscompare.validate(p) == p  # idempotent
    argvs = dnscompare.build_argv(p)
    assert [a[5] for a in argvs] == [
        "@1.1.1.1",
        "@8.8.8.8",
        "@9.9.9.9",
        "@192.168.1.1",
        "@dns.quad9.net",
    ]
    assert all(a[-2:] == ["-q", "fedoraproject.org"] for a in argvs)


@pytest.mark.parametrize(
    "params",
    [
        {"name": "a.org", "use_1_1_1_1": False, "use_8_8_8_8": False, "use_9_9_9_9": False},
        {"name": "a.org", "custom": "1.1.1.1;id"},
        {"name": "a.org", "custom": "-p 53"},
        {"name": "a.org", "custom": " ".join(f"10.0.0.{i}" for i in range(10))},
        {"name": "$(id)"},
    ],
)
def test_dnscompare_rejects(params):
    with pytest.raises(ValidationError):
        dnscompare.validate(params)


def test_dnscompare_compare_marks_differences():
    from netpulse.tools import dig

    a = dig.parse(fixture("dig_yaml_a.txt"))
    nx = dig.parse(fixture("dig_yaml_nxdomain.txt"))
    s = dnscompare.compare({"r1": a, "r2": a, "r3": nx})
    assert not s["consistent"] and s["status"] == "warning"
    assert [r["matches"] for r in s["rows"]] == [True, True, False]
    same = dnscompare.compare({"r1": a, "r2": a})
    assert same["consistent"] and same["status"] == "ok"


# ------------------------------------------------------------------ port check
def test_portcheck_validate():
    assert portcheck.validate({"host": "a.org", "preset": "web"})["ports"] == [80, 443]
    assert portcheck.validate({"host": "a.org", "preset": "custom", "ports": "22,22, 8080"})[
        "ports"
    ] == [22, 8080]
    for bad in ({"host": "a.org", "preset": "custom", "ports": "1-1000"},
                {"host": "a.org", "preset": "all"},
                {"host": "a.org", "preset": "custom", "ports": ",".join(map(str, range(1, 12)))},
                {"host": "$(id)", "preset": "web"}):  # fmt: skip
        with pytest.raises(ValidationError):
            portcheck.validate(bad)


def test_portcheck_open_and_closed_locally():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    open_port = listener.getsockname()[1]
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()  # nothing listens here now
    try:
        mgr = JobManager()
        params = portcheck.validate(
            {"host": "127.0.0.1", "preset": "custom", "ports": [open_port, closed_port]}
        )
        job = mgr.submit("portcheck", "t", params, portcheck.run, 20)
        mgr.subscribe(job)
        deadline = time.monotonic() + 10
        while not job.finished and time.monotonic() < deadline:
            time.sleep(0.05)
        states = {r["port"]: r["state"] for r in job.summary["results"]}
        assert states == {open_port: "open", closed_port: "closed"}
        assert job.summary["status"] == "warning"
    finally:
        listener.close()


def test_portcheck_filtered(monkeypatch):
    def fake_connect(self, addr):
        raise TimeoutError

    monkeypatch.setattr(socket.socket, "connect", fake_connect)
    r = portcheck.check_port(socket.AF_INET, "192.0.2.1", 443, 0.5)
    assert r["state"] == "filtered" and r["time_ms"] is None


# ------------------------------------------------------------------ HTTP check
def test_httpcheck_argv():
    argv = httpcheck.build_argv({"url": "fedoraproject.org"})
    assert argv[:2] == ["curl", "-q"]  # -q first: ignore ~/.curlrc
    assert argv[-2:] == ["--url", "https://fedoraproject.org/"]
    assert "--location" in argv and "--insecure" not in argv
    assert argv[argv.index("--proto") + 1] == "=http,https"
    argv = httpcheck.build_argv(
        {"url": "http://a.org/x", "method": "HEAD", "follow": False, "insecure": True}
    )
    assert "--head" in argv and "--location" not in argv and "--insecure" in argv


@pytest.mark.parametrize(
    "bad",
    ["file:///etc/passwd", "-K /etc/passwd", "https://a.org/ -o /tmp/x", "https://$(id)/",
     "gopher://a.org/", "https://a.org/\n-o x", "dict://a.org/", "--config=/x"],
)  # fmt: skip
def test_httpcheck_rejects(bad):
    with pytest.raises(ValidationError):
        httpcheck.build_argv({"url": bad})


def test_httpcheck_parse_single_request_breakdown():
    s = httpcheck.parse(fixture("curl_https_ok.txt"))
    assert s["status"] == "ok" and s["http_code"] == 200 and s["http_version"] == "2"
    labels = [p["label"] for p in s["timing"]["phases"]]
    assert labels == ["DNS", "Connect", "TLS", "Server wait", "Transfer"]
    assert s["timing"]["exact"]
    total = sum(p["ms"] for p in s["timing"]["phases"])
    assert abs(total - s["timing"]["total_ms"]) < 2  # phases add up to the total
    assert any(k.lower() == "content-type" for k, _ in s["headers"])


def test_httpcheck_parse_redirects():
    s = httpcheck.parse(fixture("curl_redirects.txt"))
    assert s["num_redirects"] == 1 and len(s["responses"]) == 2
    assert s["responses"][0]["status"] == 302
    assert s["responses"][0]["location"] == "https://fedoraproject.org/"
    assert not s["timing"]["exact"]
    assert [p["label"] for p in s["timing"]["phases"]] == ["Redirects (1)", "Final request"]
    nr = httpcheck.parse(fixture("curl_noredirect.txt"))
    assert nr["http_code"] == 302 and nr["status"] == "warning"


@pytest.mark.parametrize(
    "name,needle",
    [
        ("curl_tls_expired.txt", "expired"),
        ("curl_unknown_host.txt", "resolve"),
        ("curl_timeout.txt", "timed out"),
        ("curl_refused.txt", "connect"),
    ],
)
def test_httpcheck_parse_errors(name, needle):
    s = httpcheck.parse(fixture(name))
    assert s["status"] == "error" and needle in s["message"]
    assert s["timing"]["phases"] == []


def test_httpcheck_parse_404():
    assert httpcheck.parse(fixture("curl_404.txt"))["status"] == "warning"


# ------------------------------------------------------------------ TLS
def test_tls_argv():
    assert tlscert.build_argv({"host": "fedoraproject.org"}) == [
        "openssl", "s_client", "-showcerts", "-connect", "fedoraproject.org:443",
        "-servername", "fedoraproject.org", "-verify_hostname", "fedoraproject.org",
    ]  # fmt: skip
    assert tlscert.build_argv({"host": "1.1.1.1", "port": 853})[-2:] == ["-verify_ip", "1.1.1.1"]
    assert "[::1]:443" in tlscert.build_argv({"host": "::1"})
    argv = tlscert.build_argv({"host": "1.1.1.1", "servername": "one.one.one.one"})
    assert argv[-4:] == ["-servername", "one.one.one.one", "-verify_hostname", "one.one.one.one"]


@pytest.mark.parametrize(
    "params",
    [
        {"host": "-connect"},
        {"host": "a.org", "port": "443 -quiet"},
        {"host": "a.org", "servername": "-x"},
        {"host": "a.org", "port": 0},
        {"host": "a.org:443"},
    ],
)
def test_tls_rejects(params):
    with pytest.raises(ValidationError):
        tlscert.build_argv(params)


def test_tls_parse_ok_with_leaf():
    info = tlscert.parse_s_client(fixture("openssl_ok.txt"))
    assert info["verify_ok"] and info["protocol"] == "TLSv1.3"
    assert len(info["chain"]) == 2 and len(info["pems"]) == 2
    leaf = tlscert.parse_x509(fixture("x509_ok.txt"))
    assert leaf["common_name"] == "*.fedoraproject.org"
    assert leaf["san"] == ["DNS:*.fedoraproject.org", "DNS:fedoraproject.org"]
    s = tlscert.evaluate(info, leaf, NOW)
    assert s["status"] == "ok" and s["days_left"] == 148 and s["expires"] == "2027-04-15"


def test_tls_expiry_warning_and_errors():
    info = tlscert.parse_s_client(fixture("openssl_ip.txt"))
    leaf = tlscert.parse_x509(fixture("x509_ip.txt"))
    assert tlscert.evaluate(info, leaf, NOW)["days_left"] == 33  # 30-day threshold: still ok
    s = tlscert.evaluate(info, leaf, datetime(2026, 12, 1, tzinfo=UTC))
    assert s["status"] == "warning" and s["days_left"] == 20
    assert "IP Address:1.1.1.1" in s["leaf"]["san"]
    for name, needle in (
        ("openssl_expired.txt", "expired"),
        ("openssl_wronghost.txt", "hostname mismatch"),
        ("openssl_selfsigned.txt", "self-signed"),
        ("openssl_refused.txt", "Connection refused"),
        ("openssl_unknown.txt", "Name or service not known"),
    ):
        s = tlscert.parse(fixture(name))
        assert s["status"] == "error" and needle in s["message"], name


def test_tls_chain_dates():
    info = tlscert.parse_s_client(fixture("openssl_expired.txt"))
    s = tlscert.evaluate(info, {}, NOW)
    assert [c["days_left"] < 0 for c in s["chain"]] == [True, False, True]


# ------------------------------------------------------------------ local info
def test_localinfo_parsers():
    ifaces = localinfo.parse_addr(fixture("local_ip_addr.json"))
    names = [i["name"] for i in ifaces]
    assert names[0] == "lo" and "eno1" in names
    eno = next(i for i in ifaces if i["name"] == "eno1")
    first = eno["addresses"][0]
    assert (first["family"], first["address"], first["prefix"]) == ("IPv4", "192.168.202.2", 24)
    routes = localinfo.parse_routes(fixture("local_ip_route.json"), "IPv4")
    assert routes[0]["dst"] == "default" and routes[0]["gateway"] == "192.168.202.1"
    dns = localinfo.parse_resolvectl(fixture("local_resolvectl.txt"))
    eno_dns = next(link for link in dns["links"] if link["link"] == "eno1")
    assert eno_dns["dns_servers"] == ["192.168.202.1"]
    assert "DNSSEC=no/unsupported" in dns["global"]["protocols"]
    socks = localinfo.parse_ss(fixture("local_ss.txt"))
    assert {"proto": "udp", "state": "UNCONN", "address": "0.0.0.0", "port": "5353"} in socks
    summary = localinfo.summarize({"interfaces": ifaces, "routes": routes, "dns": dns})
    assert summary["status"] == "ok" and summary["dns_servers"] == ["192.168.202.1"]
    assert localinfo.summarize({"interfaces": ifaces, "routes": []})["status"] == "warning"


def test_localinfo_resolv_conf_fallback():
    d = localinfo.parse_resolv_conf("# x\nnameserver 127.0.0.53\nsearch lan example.org\n")
    assert d["global"]["dns_servers"] == ["127.0.0.53"]
    assert d["global"]["dns_domain"] == ["lan", "example.org"]


def test_localinfo_argv():
    assert localinfo.build_argv({}) == [
        localinfo.ADDR_ARGV, localinfo.ROUTE4_ARGV, localinfo.ROUTE6_ARGV, localinfo.DNS_ARGV,
    ]  # fmt: skip
    assert localinfo.build_argv({"sockets": True})[-1] == localinfo.SOCKETS_ARGV


# ------------------------------------------------------------------ CIDR
def test_cidr_ipv4():
    s = cidr.calculate("192.168.1.10/24")
    assert (s["network"], s["netmask"], s["broadcast"]) == (
        "192.168.1.0/24",
        "255.255.255.0",
        "192.168.1.255",
    )
    assert (s["first_host"], s["last_host"], s["usable_hosts"]) == (
        "192.168.1.1",
        "192.168.1.254",
        "254",
    )
    assert s["wildcard"] == "0.0.0.255" and s["address_kind"] == ["private"]
    p31 = cidr.calculate("10.0.0.0/31")
    assert p31["usable_hosts"] == "2" and p31["broadcast"] is None
    assert cidr.calculate("100.64.1.1/10")["address_kind"][-1].startswith("carrier-grade")


def test_cidr_ipv6_and_split():
    s = cidr.calculate("2001:db8::1/48", 52)
    assert s["network"] == "2001:db8::/48" and s["size"] == "2^80"
    assert s["subnet_count"] == "16" and s["subnets"][1]["subnet"] == "2001:db8:0:1000::/52"
    big = cidr.calculate("10.0.0.0/8", 30)
    assert len(big["subnets"]) == cidr.MAX_SUBNETS and big["subnets_truncated"]


def test_cidr_validate():
    assert cidr.validate({"network": "10.0.0.1 255.255.0.0"})["network"] == "10.0.0.1/16"
    for bad in ({"network": "10.0.0.0/8", "split": 4}, {"network": "10.0.0.0/8", "split": 40},
                {"network": "10.0.0.0/33"}, {"network": "$(id)"}):  # fmt: skip
        with pytest.raises(ValidationError):
            cidr.validate(bad)


# ------------------------------------------------------------------ quick diagnose
def test_diagnose_plan_for_name_and_ip(monkeypatch):
    steps = diagnose.plan("fedoraproject.org")
    assert set(steps) == set(diagnose.CHECKS)
    assert steps["dns_a"][0][-4:] == ["-t", "A", "-q", "fedoraproject.org"]
    assert steps["http"][0][-1] == "https://fedoraproject.org/"
    ip_steps = diagnose.plan("1.1.1.1")
    assert ip_steps["dns_a"][0] is None and ip_steps["http"][0][-1] == "http://1.1.1.1/"
    assert diagnose.plan("::1")["http"][0][-1] == "http://[::1]/"


def test_diagnose_report_verdict():
    from netpulse.tools import ping

    checks = {"ping": ping.parse(fixture("ping_v4_internet.txt")),
              "dns_a": {"skipped": True, "status": "ok", "message": "skipped"},
              "http": httpcheck.parse(fixture("curl_refused.txt"))}  # fmt: skip
    r = diagnose.report("x", checks, [])
    assert r["status"] == "error" and "HTTP(S)" in r["message"]
    rows = {row["check"]: row for row in r["rows"]}
    assert rows["ping"]["finding"].startswith("0% loss")
    assert rows["dns_a"]["status"] == "skipped" and rows["traceroute"]["status"] == "running"


@pytest.mark.parametrize("bad", INJECTIONS)
def test_diagnose_rejects(bad):
    with pytest.raises(ValidationError):
        diagnose.build_argv({"host": bad})


# ------------------------------------------------------------------ every tool
def test_every_tool_is_registered_with_a_group():
    from netpulse import tools
    from netpulse.tools.base import GROUPS

    reg = tools.load_all()
    assert len(reg) == 15
    assert all(t.group in GROUPS for t in reg.values())
