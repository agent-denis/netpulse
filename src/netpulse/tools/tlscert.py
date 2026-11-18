# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""TLS certificate check with ``openssl s_client`` (+ ``openssl x509`` for the leaf)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from netpulse import validators as v
from netpulse.jobs import JobContext
from netpulse.tools.base import Params, Summary, Tool

TIMEOUT_S = 20
WARN_DAYS = 30

_CHAIN_RE = re.compile(r"^\s*(\d+) s:(.*)$")
_PEM_RE = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


def validate(params: Params) -> Params:
    host = v.host_or_ip(params.get("host"), "host")
    sni = params.get("servername") or ""
    return {
        "host": host,
        "port": v.port(443 if params.get("port") in (None, "") else params["port"], "port"),
        "servername": v.hostname(sni, "servername") if sni else "",
    }


def _connect_target(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    argv = ["openssl", "s_client", "-showcerts", "-connect", _connect_target(p["host"], p["port"])]
    name = p["servername"] or (p["host"] if not v.is_ip(p["host"]) else "")
    if name:
        argv += ["-servername", name, "-verify_hostname", name]
    else:
        argv += ["-verify_ip", p["host"]]
    return argv


X509_ARGV = [
    "openssl", "x509", "-noout", "-subject", "-issuer", "-serial", "-dates",
    "-fingerprint", "-sha256", "-ext", "subjectAltName", "-nameopt", "RFC2253",
]  # fmt: skip


def timeout(params: Params) -> float:
    return TIMEOUT_S + 10


def parse_date(text: str) -> datetime | None:
    text = re.sub(r"\s+", " ", text.strip())
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S.%f %Y %Z"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_s_client(output: str) -> Summary:
    chain: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    info: dict[str, Any] = {"verify_ok": None, "verify_error": None}
    errors: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if m := _CHAIN_RE.match(raw):
            current = {"depth": int(m.group(1)), "subject": m.group(2).strip()}
            chain.append(current)
        elif current is not None and line.startswith("i:"):
            current["issuer"] = line[2:].strip()
        elif current is not None and line.startswith("a:"):
            current["key"] = line[2:].strip()
        elif current is not None and line.startswith("v:NotBefore:"):
            nb, _, na = line[len("v:NotBefore:") :].partition("; NotAfter:")
            current["not_before"] = nb.strip()
            current["not_after"] = na.strip()
        elif line == "---":
            current = None
        elif line.startswith("Verification: OK"):
            info["verify_ok"] = True
        elif line.startswith("Verification error:"):
            info["verify_ok"] = False
            info["verify_error"] = line.split(":", 1)[1].strip()
        elif line.startswith("Verify return code:"):
            code = line.split(":", 1)[1].strip()
            info["verify_code"] = code
            if info["verify_ok"] is None:
                info["verify_ok"] = code.startswith("0 ")
        elif m := re.match(r"^New, (\S+), Cipher is (\S+)", line):
            info["protocol"], info["cipher"] = m.group(1), m.group(2)
        elif line.startswith("Protocol:") or line.startswith("Protocol  :"):
            info.setdefault("protocol", line.split(":", 1)[1].strip())
        elif line.startswith("Peer Temp Key:"):
            info["temp_key"] = line.split(":", 1)[1].strip()
        elif line.startswith("Server public key is"):
            info["public_key"] = line[len("Server public key is") :].strip()
        elif line.startswith(("Connecting to", "CONNECTED(")):
            info.setdefault("connected_to", line)
        elif ":error:" in line:
            # 00..:error:8000006F:system library:BIO_connect:Connection refused:file:line:extra
            parts = line.split(":")
            generic = ("connect error", "system lib", "calling connect()", "")
            reason = next(
                (c.strip() for c in (parts[5:6] + parts[-1:]) if c.strip() not in generic), None
            )
            if reason and reason not in errors:
                errors.append(reason)
        elif line.startswith("connect:errno") and not errors:
            errors.append(line)
    pems = _PEM_RE.findall(output)
    return {**info, "chain": chain, "pems": pems, "errors": errors}


def parse_x509(output: str) -> dict[str, Any]:
    leaf: dict[str, Any] = {"san": []}
    lines = output.splitlines()
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("subject="):
            leaf["subject"] = line[len("subject=") :]
        elif line.startswith("issuer="):
            leaf["issuer"] = line[len("issuer=") :]
        elif line.startswith("serial="):
            leaf["serial"] = line[len("serial=") :]
        elif line.startswith("notBefore="):
            leaf["not_before"] = line[len("notBefore=") :]
        elif line.startswith("notAfter="):
            leaf["not_after"] = line[len("notAfter=") :]
        elif "Fingerprint=" in line:
            leaf["sha256"] = line.split("=", 1)[1]
        elif line.startswith("X509v3 Subject Alternative Name") and i + 1 < len(lines):
            leaf["san"] = [s.strip() for s in lines[i + 1].split(",") if s.strip()]
    cn = re.search(r"(?:^|,)CN=([^,]+)", leaf.get("subject", ""))
    leaf["common_name"] = cn.group(1) if cn else None
    return leaf


def _leaf_from_chain(cert: dict[str, Any]) -> dict[str, Any]:
    keys = ("subject", "issuer", "not_before", "not_after")
    return {k: cert.get(k) for k in keys}


def evaluate(info: Summary, leaf: dict[str, Any], now: datetime | None = None) -> Summary:
    now = now or datetime.now(UTC)
    summary: Summary = {
        "protocol": info.get("protocol"),
        "cipher": info.get("cipher"),
        "temp_key": info.get("temp_key"),
        "public_key": info.get("public_key"),
        "verify_ok": info.get("verify_ok"),
        "verify_error": info.get("verify_error"),
        "chain": info.get("chain", []),
        "leaf": leaf,
        "errors": info.get("errors", []),
    }
    not_after = parse_date(leaf.get("not_after", "")) if leaf.get("not_after") else None
    not_before = parse_date(leaf.get("not_before", "")) if leaf.get("not_before") else None
    if not_after:
        summary["days_left"] = (not_after - now).days
        summary["expires"] = not_after.date().isoformat()
    if not_before:
        summary["valid_from"] = not_before.date().isoformat()
    for cert in summary["chain"]:
        exp = parse_date(cert.get("not_after", "")) if cert.get("not_after") else None
        cert["days_left"] = (exp - now).days if exp else None

    if not summary["chain"] and not leaf.get("subject"):
        summary["status"] = "error"
        summary["message"] = "; ".join(summary["errors"]) or "no TLS connection could be made"
    elif summary["verify_ok"] is False:
        summary["status"] = "error"
        summary["message"] = (
            f"certificate is not trusted: {summary['verify_error'] or 'verification failed'}"
        )
    elif summary.get("days_left") is not None and summary["days_left"] < 0:
        summary["status"], summary["message"] = "error", "the certificate has expired"
    elif summary.get("days_left") is not None and summary["days_left"] < WARN_DAYS:
        summary["status"] = "warning"
        summary["message"] = f"valid, but expires in {summary['days_left']} days"
    else:
        summary["status"] = "ok"
        days = summary.get("days_left")
        summary["message"] = "valid and trusted" + (
            f", {days} days left" if days is not None else ""
        )
    return summary


def parse(output: str) -> Summary:
    """Parse s_client output (leaf details come from the chain lines only)."""
    info = parse_s_client(output)
    leaf: dict[str, Any] = {"san": []}
    if info["chain"]:
        first = info["chain"][0]
        leaf.update(_leaf_from_chain(first))
    summary = evaluate(info, leaf)
    summary["exit_code"] = None
    return summary


def run(ctx: JobContext, params: Params) -> Summary:
    p = params
    result = ctx.run(build_argv(p), timeout=TIMEOUT_S)
    info = parse_s_client(result.output)
    leaf: dict[str, Any] = {"san": []}
    if info["pems"]:
        x = ctx.run(X509_ARGV, timeout=10, input_text=info["pems"][0] + "\n", label="leaf")
        leaf = parse_x509(x.output)
    elif info["chain"]:
        first = info["chain"][0]
        leaf.update(_leaf_from_chain(first))
    summary = evaluate(info, leaf)
    summary["exit_code"] = result.returncode
    summary["host"], summary["port"] = p["host"], p["port"]
    if result.timed_out:
        summary["status"] = "error"
        summary["message"] = f"no TLS handshake within {TIMEOUT_S} s (port closed or filtered?)"
    return summary


TOOL = Tool(
    name="tlscert",
    title="TLS certificate",
    group="Web & TLS",
    description="Inspect a server's certificate: names, issuer, validity, chain, protocol "
    "and cipher.",
    validate=validate,
    run=run,
    timeout=timeout,
    binaries=("openssl",),
    target=lambda p: f"{p['host']}:{p['port']}",
)
