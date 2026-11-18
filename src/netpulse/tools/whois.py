# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Denis
"""whois for domains and IP addresses."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from netpulse import validators as v
from netpulse.tools.base import Params, Summary, Tool, command_runner

TIMEOUT_S = 40

# Field name variants used by ICANN registries, RIRs (ARIN/RIPE/APNIC/LACNIC/AFRINIC) and ccTLDs.
FIELDS: dict[str, tuple[str, ...]] = {
    "domain": ("domain name", "domain"),
    "registrar": ("registrar", "sponsoring registrar", "registrar name"),
    "created": ("creation date", "created", "registered on", "registration time",
                "domain registration date", "created date", "registered", "regdate"),
    "updated": ("updated date", "last updated", "last-modified", "changed", "last modified",
                "updated"),
    "expires": ("registry expiry date", "registrar registration expiration date",
                "expiration date", "expiry date", "expires", "paid-till", "expire date",
                "expires on", "renewal date"),
    "status": ("domain status", "status", "registration status"),
    "name_servers": ("name server", "nserver", "name servers", "nameservers", "name servers"),
    "dnssec": ("dnssec",),
    "org": ("registrant organization", "orgname", "org-name", "organisation", "organization",
            "owner", "descr"),
    "netname": ("netname", "net-name"),
    "network": ("cidr", "inetnum", "inet6num", "netrange", "route", "route6"),
    "country": ("country", "registrant country"),
    "abuse": ("registrar abuse contact email", "orgabuseemail", "abuse-mailbox",
              "abuse contact email", "abuse email"),
    "whois_server": ("registrar whois server", "refer", "whois"),
}  # fmt: skip
MULTI = {"name_servers", "status"}
_LINE_RE = re.compile(r"^\s{0,12}([A-Za-z][A-Za-z0-9 ./_-]{0,60}?)\s*:\s+(\S.*)$")
_BLOCK_RE = re.compile(r"^(\s*)([A-Za-z][A-Za-z0-9 ./_-]{0,60}?):\s*$")
_ABUSE_RE = re.compile(r"Abuse contact for '[^']+' is '([^']+)'")
_NOMATCH = ("no match", "not found", "no entries found", "no data found", "status: free",
            "no object found", "is available for registration", "not registered")  # fmt: skip


def validate(params: Params) -> Params:
    query = v.safe_text(params.get("query"), "query", max_len=254)
    if v.is_ip(query):
        return {"query": str(v.ip_address(query, "query"))}
    if "/" in query:  # a network, e.g. 192.0.2.0/24
        try:
            return {"query": str(v.cidr(query, "query").network)}
        except v.ValidationError:
            raise v.ValidationError("query", "is not a valid domain, IP or network") from None
    return {"query": v.hostname(query, "query").rstrip(".")}


def build_argv(params: Params) -> list[str]:
    p = validate(params)
    # -H hides the long legal disclaimers.
    return ["whois", "-H", "--", p["query"]]


def timeout(params: Params) -> float:
    return TIMEOUT_S


def _date(value: str) -> str | None:
    """Normalise a whois date to YYYY-MM-DD where we can."""
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%b-%Y", "%Y.%m.%d", "%d.%m.%Y",
                "%Y/%m/%d", "%Y%m%d"):  # fmt: skip
        try:
            return datetime.strptime(value.split(" (")[0].strip(), fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    return m.group(1) if m else None


def _store(found: dict[str, Any], key: str, value: str) -> None:
    """Record *value* under the summary field that *key* is a variant of."""
    if value.lower().startswith(("redacted", "data protected", "not disclosed")):
        return
    for field, names in FIELDS.items():
        if key in names:
            if field in MULTI:
                item = value.split()[0] if field == "status" else value.split()[0].lower()
                found.setdefault(field, [])
                if item not in found[field]:
                    found[field].append(item)
            else:
                found.setdefault(field, value)
            return


def parse(output: str, today: datetime | None = None) -> Summary:
    found: dict[str, Any] = {}
    errors: list[str] = []
    lowered = output.lower()
    pending: tuple[str, int] | None = None  # "Key:" alone, values on indented lines (.uk)
    for raw in output.splitlines():
        indent = len(raw) - len(raw.lstrip())
        if m := _BLOCK_RE.match(raw):
            pending = (m.group(2).strip().lower(), len(m.group(1)))
            continue
        if pending and raw.strip() and indent > pending[1] and not _LINE_RE.match(raw):
            _store(found, pending[0], raw.strip())
            continue
        if not raw.strip() or indent <= (pending[1] if pending else -1):
            pending = None
        if m := _ABUSE_RE.search(raw):
            found.setdefault("abuse", m.group(1))
            continue
        if raw.startswith(("%", "#", ">>>")):
            continue
        if raw.lower().startswith(("fgets:", "connect:", "getaddrinfo", "whois:")):
            errors.append(raw.strip())
            continue
        m = _LINE_RE.match(raw)
        if not m:
            continue
        _store(found, m.group(1).strip().lower(), m.group(2).strip())
    for key in ("created", "updated", "expires"):
        if key in found:
            found[f"{key}_date"] = _date(found[key])
    now = today or datetime.now(UTC)
    summary: Summary = {**found, "errors": errors}
    if found.get("expires_date"):
        exp = datetime.fromisoformat(found["expires_date"]).replace(tzinfo=UTC)
        summary["days_to_expiry"] = (exp - now).days
    is_match = bool(set(found) & {"registrar", "created", "netname", "network", "name_servers"})
    if errors and not is_match:
        summary["status"], summary["message"] = "error", "; ".join(errors)
    elif not is_match and any(s in lowered for s in _NOMATCH):
        summary["status"], summary["message"] = "warning", "no match: not registered, or unknown"
    elif not is_match:
        summary["status"] = "warning"
        summary["message"] = "no key fields recognised; see the raw output"
    elif summary.get("days_to_expiry") is not None and summary["days_to_expiry"] < 30:
        summary["status"] = "warning"
        summary["message"] = f"expires in {summary['days_to_expiry']} days"
    else:
        summary["status"] = "ok"
        summary["message"] = (
            found.get("registrar")
            or found.get("org")
            or found.get("netname")
            or found.get("domain", "")
        )
    return summary


TOOL = Tool(
    name="whois",
    title="whois",
    group="DNS",
    description="Registration details for a domain, or the owner of an IP address range.",
    validate=validate,
    run=command_runner(build_argv, parse, timeout),
    timeout=timeout,
    binaries=("whois",),
    target=lambda p: p["query"],
)
