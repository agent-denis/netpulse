# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Server-side input validation.

Every value that ends up in a command line goes through one of these
functions first. They return a *normalised* value (e.g. punycode hostnames)
or raise :class:`ValidationError`. Nothing here trusts the browser.
"""

from __future__ import annotations

import ipaddress
import math
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

MAX_NAME_LEN = 253
MAX_LABEL_LEN = 63

_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
# DNS owner names (dig/nslookup/host) may also contain underscores: _dmarc, _sip._tcp …
_DNS_LABEL_RE = re.compile(r"^[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?$")
_IFACE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")

# Script combinations that are legitimately used together inside one label.
_ALLOWED_SCRIPT_MIXES = (
    {"CJK", "HIRAGANA", "KATAKANA"},
    {"CJK", "HANGUL"},
)


class ValidationError(ValueError):
    """Raised when user input is rejected. The message is shown to the user."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


# --------------------------------------------------------------------------- basics


def safe_text(value: Any, field: str, *, max_len: int = 255, allow_empty: bool = False) -> str:
    """A plain string with no control characters, no whitespace at the ends and no leading '-'."""
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValidationError(field, "must be text")
    value = value.strip()
    if not value:
        if allow_empty:
            return ""
        raise ValidationError(field, "is required")
    if len(value) > max_len:
        raise ValidationError(field, f"is too long (max {max_len} characters)")
    if any(unicodedata.category(c).startswith("C") for c in value):
        raise ValidationError(field, "contains control characters")
    if value.startswith("-"):
        raise ValidationError(field, "must not start with '-'")
    return value


def _no_spaces(value: str, field: str) -> str:
    if any(c.isspace() for c in value):
        raise ValidationError(field, "must not contain spaces")
    return value


def choice(value: Any, allowed: Iterable[str], field: str, *, default: str | None = None) -> str:
    allowed = tuple(allowed)
    if value in (None, "") and default is not None:
        return default
    if not isinstance(value, str) or value not in allowed:
        raise ValidationError(field, f"must be one of: {', '.join(allowed)}")
    return value


def boolean(value: Any, field: str, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if value in ("1", "true", "on", 1):
        return True
    if value in ("0", "false", "off", 0):
        return False
    raise ValidationError(field, "must be true or false")


def int_range(value: Any, lo: int, hi: int, field: str, *, default: int) -> int:
    """Parse an integer and clamp it to [lo, hi]."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValidationError(field, "must be a whole number")
    try:
        number = int(str(value).strip(), 10) if not isinstance(value, int) else value
    except ValueError:
        raise ValidationError(field, "must be a whole number") from None
    return max(lo, min(hi, number))


def float_range(value: Any, lo: float, hi: float, field: str, *, default: float) -> float:
    """Parse a number and clamp it to [lo, hi]."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValidationError(field, "must be a number")
    try:
        number = float(str(value).strip()) if not isinstance(value, int | float) else float(value)
    except ValueError:
        raise ValidationError(field, "must be a number") from None
    if not math.isfinite(number):
        raise ValidationError(field, "must be a finite number")
    return max(lo, min(hi, number))


# --------------------------------------------------------------------------- addresses


def ip_address(
    value: Any, field: str = "address", *, allow_scope: bool = False
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    text = _no_spaces(safe_text(value, field, max_len=64), field)
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if "%" in text:
        if not allow_scope:
            raise ValidationError(field, "zone/scope IDs are not allowed here")
        scope = text.split("%", 1)[1]
        if not _IFACE_RE.match(scope):
            raise ValidationError(field, "invalid interface name in scope ID")
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        raise ValidationError(field, "is not a valid IPv4 or IPv6 address") from None
    if addr.version == 4 and "%" in text:
        raise ValidationError(field, "scope IDs only apply to IPv6")
    return addr


def _scripts(label: str) -> set[str]:
    scripts: set[str] = set()
    for ch in label:
        if ch.isascii() and (ch.isalnum() or ch in "-_"):
            if ch.isalpha():
                scripts.add("LATIN")
            continue
        name = unicodedata.name(ch, "")
        if not name:
            scripts.add("UNKNOWN")
            continue
        word = name.split()[0]
        if word in ("COMBINING", "DIGIT", "HYPHEN-MINUS"):
            continue
        scripts.add(word)
    return scripts


def _check_mixed_script(unicode_name: str, field: str) -> None:
    for label in unicode_name.split("."):
        if label.isascii():
            continue
        scripts = _scripts(label)
        if len(scripts) <= 1:
            continue
        if any(scripts <= mix for mix in _ALLOWED_SCRIPT_MIXES):
            continue
        raise ValidationError(
            field,
            f"label '{label}' mixes {' and '.join(sorted(s.title() for s in scripts))} "
            "characters, which is a common look-alike (homoglyph) trick",
        )


def _to_ascii(name: str, field: str) -> str:
    """IDN → punycode via the stdlib ``idna`` codec (IDNA 2003 + nameprep)."""
    if name.isascii():
        name = name.lower()
        # Already-punycoded labels get the same homoglyph check as Unicode input.
        for label in name.split("."):
            if label.startswith("xn--"):
                try:
                    _check_mixed_script(label.encode("ascii").decode("idna"), field)
                except UnicodeError:
                    raise ValidationError(field, f"label '{label}' is invalid punycode") from None
        return name
    _check_mixed_script(name, field)
    try:
        return name.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValidationError(field, "is not a valid internationalised domain name") from None


def hostname(value: Any, field: str = "host", *, dns_name: bool = False) -> str:
    """Validate an RFC 1123 hostname (or, with *dns_name*, a DNS owner name).

    Returns the lowercase ASCII (punycode) form. A trailing dot is kept.
    """
    text = _no_spaces(safe_text(value, field, max_len=MAX_NAME_LEN + 1), field)
    trailing_dot = text.endswith(".") and len(text) > 1
    core = text[:-1] if trailing_dot else text
    if dns_name and core in (".", ""):
        return "."
    ascii_name = _to_ascii(core, field)
    if len(ascii_name) > MAX_NAME_LEN:
        raise ValidationError(field, "is too long (max 253 characters)")
    labels = ascii_name.split(".")
    pattern = _DNS_LABEL_RE if dns_name else _LABEL_RE
    for label in labels:
        if not label:
            raise ValidationError(field, "contains an empty label ('..')")
        if len(label) > MAX_LABEL_LEN:
            raise ValidationError(field, "has a label longer than 63 characters")
        if not pattern.match(label):
            raise ValidationError(
                field,
                "may only contain letters, digits and hyphens (not at the start or end of a label)",
            )
    if len(labels) > 1 and labels[-1].isdigit():
        raise ValidationError(field, "looks like an IP address but is not a valid one")
    return ascii_name + ("." if trailing_dot else "")


def host_or_ip(value: Any, field: str = "host", *, allow_scope: bool = False) -> str:
    """A hostname or IP literal. Returns the normalised string."""
    text = safe_text(value, field, max_len=MAX_NAME_LEN + 1)
    candidate = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    if ":" in candidate or re.fullmatch(r"[0-9.]+", candidate):
        if "%" in candidate:
            addr = ip_address(candidate, field, allow_scope=allow_scope)
            return f"{addr}"
        return str(ip_address(candidate, field))
    return hostname(text, field)


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return True


def port(value: Any, field: str = "port") -> int:
    if isinstance(value, bool):
        raise ValidationError(field, "must be a port number")
    try:
        number = int(str(value).strip(), 10)
    except ValueError:
        raise ValidationError(field, "must be a port number") from None
    if not 1 <= number <= 65535:
        raise ValidationError(field, "must be between 1 and 65535")
    return number


def port_list(value: Any, field: str = "ports", *, max_ports: int = 10) -> list[int]:
    """'22, 80,443' or [22, 80] → [22, 80, 443] (deduplicated, order kept)."""
    if isinstance(value, str):
        items: list[Any] = [p for p in re.split(r"[,\s]+", value.strip()) if p]
    elif isinstance(value, list):
        items = value
    else:
        raise ValidationError(field, "must be a list of ports")
    if not items:
        raise ValidationError(field, "at least one port is required")
    ports: list[int] = []
    for item in items:
        number = port(item, field)
        if number not in ports:
            ports.append(number)
    if len(ports) > max_ports:
        raise ValidationError(field, f"at most {max_ports} ports per check")
    return ports


def cidr(value: Any, field: str = "network") -> ipaddress.IPv4Interface | ipaddress.IPv6Interface:
    """'192.168.1.10/24', '10.0.0.0 255.0.0.0' or '2001:db8::/48' → interface object."""
    text = safe_text(value, field, max_len=100)
    text = re.sub(r"\s+", " ", text)
    if " " in text:  # "address netmask"
        addr, _, mask = text.partition(" ")
        text = f"{addr}/{mask}"
    if "/" not in text:
        addr = ip_address(text, field)
        text = f"{addr}/{addr.max_prefixlen}"
    try:
        return ipaddress.ip_interface(text)
    except ValueError:
        raise ValidationError(field, "is not a valid network (e.g. 192.168.1.0/24)") from None


def url(value: Any, field: str = "url") -> str:
    """An http(s) URL with a validated host. Returns the normalised URL."""
    text = _no_spaces(safe_text(value, field, max_len=2048), field)
    if "://" not in text:
        text = "https://" + text
    match = re.fullmatch(
        r"(?i)(https?)://(\[[0-9a-f:.]+\]|[^/:?#\[\]@]+)(?::(\d{1,5}))?([/?#][^\s]*)?", text
    )
    if not match:
        raise ValidationError(field, "must be an http:// or https:// URL")
    scheme, host, port_s, rest = match.groups()
    if host.startswith("["):
        host = f"[{ip_address(host[1:-1], field)}]"
    else:
        host = host_or_ip(host, field)
        if ":" in host:
            host = f"[{host}]"
    port_part = f":{port(port_s, field)}" if port_s else ""
    rest = rest or "/"
    if any(ord(c) > 126 or ord(c) < 33 for c in rest):
        raise ValidationError(field, "path must be URL-encoded ASCII")
    return f"{scheme.lower()}://{host}{port_part}{rest}"


def resolver(value: Any, custom: Any, field: str = "resolver") -> str | None:
    """'system' → None, preset or custom → normalised server address/hostname."""
    presets = {"system", "1.1.1.1", "8.8.8.8", "9.9.9.9", "custom"}
    choice_value = choice(value, sorted(presets), field, default="system")
    if choice_value == "system":
        return None
    if choice_value == "custom":
        return host_or_ip(custom, "custom resolver")
    return choice_value
