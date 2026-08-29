"""HMRC fraud prevention headers (Gov-Client-* / Gov-Vendor-*).

HMRC rejects — and, worse, silently deprioritises — submissions whose
fraud prevention headers are wrong. This app is
`MOBILE_APP_VIA_SERVER`: the phone collects the device facts, our API
adds the server-side ones and forwards the call.

The phone sends its half as one base64url-encoded JSON object in the
`X-ASETS-Device` header. Everything HMRC wants that only the server can
know (the caller's public IP, our own IP, the forwarded chain) is filled
in here.

Reference: developer.service.hmrc.gov.uk/guides/fraud-prevention/
           connection-method/mobile-app-via-server/
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

CONNECTION_METHOD = "MOBILE_APP_VIA_SERVER"

PRODUCT_NAME = os.environ.get("HMRC_PRODUCT_NAME", "ASETS")
SERVER_VERSION = os.environ.get("HMRC_SERVER_VERSION", "1.0.0")
# Our own outbound address, as HMRC sees it. HMRC requires it, and it has
# to be the real one — a serverless platform has no fixed egress IP, so
# rather than demanding a paid static IP we ask what ours is, once, at
# startup, and cache it for the life of the instance. An explicit
# HMRC_VENDOR_PUBLIC_IP always wins.
_vendor_public_ip = os.environ.get("HMRC_VENDOR_PUBLIC_IP", "").strip()

# Plain-text echo services: no parsing, no API key, no third-party SDK.
EGRESS_PROBES = ("https://checkip.amazonaws.com", "https://api.ipify.org")


def vendor_public_ip() -> str:
    return _vendor_public_ip


async def resolve_vendor_public_ip(timeout: float = 5.0) -> str:
    """Best effort, at startup. Failing costs us one header, not the app."""
    global _vendor_public_ip
    if _vendor_public_ip:
        return _vendor_public_ip
    import httpx
    for url in EGRESS_PROBES:
        try:
            async with httpx.AsyncClient(timeout=timeout) as http:
                text = (await http.get(url)).text.strip()
            ipaddress.ip_address(text)          # raises unless it really is one
            _vendor_public_ip = text
            return text
        except Exception:
            continue
    return ""

_UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
_TZ_RE = re.compile(r"^UTC[+-]\d{2}:\d{2}$")


def _now_stamp() -> str:
    """HMRC wants yyyy-MM-ddThh:mm:ss.sssZ — milliseconds, not micros."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def _enc(value: str) -> str:
    return quote(str(value), safe="")


def decode_device_header(raw: Optional[str]) -> dict:
    """Parse X-ASETS-Device. A malformed header yields {} rather than an
    error: the submission still goes out, just with fewer headers, and
    the caller can see what was missing."""
    if not raw:
        return {}
    try:
        padded = raw + "=" * (-len(raw) % 4)
        return json.loads(base64.urlsafe_b64decode(padded).decode())
    except Exception:
        return {}


def _ips(values: Any) -> str:
    out = []
    for v in values or []:
        try:
            ip = ipaddress.ip_address(str(v))
        except ValueError:
            continue
        # IPv6 must be percent-encoded (the colons).
        out.append(_enc(str(ip)) if ip.version == 6 else str(ip))
    return ",".join(out)


def build_headers(
    device: dict,
    *,
    user_id: str,
    client_ip: str = "",
    client_port: Optional[int] = None,
) -> dict:
    """Assemble the header set. Only headers we can populate honestly are
    returned — HMRC would rather have a header absent than invented."""
    headers: dict[str, str] = {
        "Gov-Client-Connection-Method": CONNECTION_METHOD,
        "Gov-Vendor-Product-Name": _enc(PRODUCT_NAME),
        # At least two components: the app and the server behind it.
        "Gov-Vendor-Version": f"asets-app={_enc(device.get('appVersion') or '1.0.0')}"
                              f"&asets-api={_enc(SERVER_VERSION)}",
        "Gov-Client-User-IDs": f"asets={_enc(user_id)}",
    }

    device_id = str(device.get("deviceId") or "")
    if _UUID_RE.match(device_id):
        headers["Gov-Client-Device-ID"] = device_id

    tz = str(device.get("timezone") or "")
    if _TZ_RE.match(tz):
        headers["Gov-Client-Timezone"] = tz

    local_ips = _ips(device.get("localIps"))
    if local_ips:
        headers["Gov-Client-Local-IPs"] = local_ips
        headers["Gov-Client-Local-IPs-Timestamp"] = device.get("localIpsTimestamp") or _now_stamp()

    screens = device.get("screens") or {}
    if screens.get("width") and screens.get("height"):
        headers["Gov-Client-Screens"] = (
            f"width={int(screens['width'])}&height={int(screens['height'])}"
            f"&scaling-factor={screens.get('scalingFactor', 1)}"
            f"&colour-depth={screens.get('colourDepth', 32)}")

    window = device.get("windowSize") or {}
    if window.get("width") and window.get("height"):
        headers["Gov-Client-Window-Size"] = f"width={int(window['width'])}&height={int(window['height'])}"

    os_info = device.get("os") or {}
    if os_info.get("family"):
        parts = [f"os-family={_enc(os_info['family'])}"]
        if os_info.get("version"):
            parts.append(f"os-version={_enc(os_info['version'])}")
        if os_info.get("manufacturer"):
            parts.append(f"device-manufacturer={_enc(os_info['manufacturer'])}")
        if os_info.get("model"):
            parts.append(f"device-model={_enc(os_info['model'])}")
        headers["Gov-Client-User-Agent"] = "&".join(parts)

    # Multi-factor is conditional: only send it when the user actually
    # used a second factor (our biometric app lock counts).
    factors = device.get("multiFactor") or []
    if factors:
        headers["Gov-Client-Multi-Factor"] = "&".join(
            f"type={_enc(f.get('type', 'OTHER'))}&timestamp={_enc(f.get('timestamp', ''))}"
            f"&unique-reference={_enc(f.get('reference', ''))}" for f in factors)

    if client_ip:
        headers["Gov-Client-Public-IP"] = client_ip
        headers["Gov-Client-Public-IP-Timestamp"] = _now_stamp()
    if client_port:
        headers["Gov-Client-Public-Port"] = str(client_port)

    vendor_ip = vendor_public_ip()
    if vendor_ip:
        headers["Gov-Vendor-Public-IP"] = vendor_ip
        # Both halves must be public IP addresses — HMRC's validator
        # rejects a hostname here, which is what a Host header gives you.
        if client_ip:
            headers["Gov-Vendor-Forwarded"] = f"by={vendor_ip}&for={client_ip}"

    return headers


# Headers HMRC expects from a mobile app behind a server. MAC addresses
# are explicitly not required for this connection method.
EXPECTED = (
    "Gov-Client-Connection-Method",
    "Gov-Client-Device-ID",
    "Gov-Client-Local-IPs",
    "Gov-Client-Local-IPs-Timestamp",
    "Gov-Client-Public-IP",
    "Gov-Client-Public-IP-Timestamp",
    "Gov-Client-Screens",
    "Gov-Client-Timezone",
    "Gov-Client-User-Agent",
    "Gov-Client-User-IDs",
    "Gov-Client-Window-Size",
    "Gov-Vendor-Product-Name",
    "Gov-Vendor-Version",
    "Gov-Vendor-Public-IP",
    "Gov-Vendor-Forwarded",
)


def missing(headers: dict) -> list:
    """Which expected headers we could not populate. Surfaced by
    /api/hmrc/status so a device problem is visible before a submission
    is rejected."""
    return [h for h in EXPECTED if h not in headers]
