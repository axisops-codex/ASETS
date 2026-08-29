"""Thin HTTP client for the HMRC Making Tax Digital APIs.

Deliberately free of database access: it knows how to talk to HMRC, not
what we store. `hmrc/service.py` joins the two.

Environments
    sandbox     https://test-api.service.hmrc.gov.uk   (default)
    production  https://api.service.hmrc.gov.uk

Production access needs HMRC's approval of the application, which is a
manual process on their side — the code path is identical.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("asets.hmrc")

SANDBOX_BASE = "https://test-api.service.hmrc.gov.uk"
PRODUCTION_BASE = "https://api.service.hmrc.gov.uk"

# API versions, pinned. HMRC ships breaking changes as new versions and
# keeps old ones alive, so pinning is safe and upgrading is deliberate.
V_BUSINESS_DETAILS = "2.0"
V_OBLIGATIONS = "3.0"
V_SELF_EMPLOYMENT = "5.0"
V_CALCULATIONS = "8.0"

SCOPES = "read:self-assessment write:self-assessment"


class HMRCError(Exception):
    """An HMRC call that did not succeed."""

    def __init__(self, status: int, message: str, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.payload = payload


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    redirect_uri: str
    environment: str

    @property
    def base_url(self) -> str:
        return PRODUCTION_BASE if self.environment == "production" else SANDBOX_BASE


def config() -> Config:
    return Config(
        client_id=os.environ.get("HMRC_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("HMRC_CLIENT_SECRET", "").strip(),
        redirect_uri=os.environ.get("HMRC_REDIRECT_URI", "").strip(),
        environment=(os.environ.get("HMRC_ENVIRONMENT", "sandbox").strip().lower()),
    )


def enabled() -> bool:
    cfg = config()
    return bool(cfg.client_id and cfg.client_secret and cfg.redirect_uri)


# Tests replace this with a factory bound to an httpx MockTransport.
_client_factory: Optional[Callable[[], httpx.AsyncClient]] = None


def set_client_factory(factory: Optional[Callable[[], httpx.AsyncClient]]) -> None:
    global _client_factory
    _client_factory = factory


def _client() -> httpx.AsyncClient:
    if _client_factory is not None:
        return _client_factory()
    return httpx.AsyncClient(timeout=30.0)


def authorization_url(state: str) -> str:
    cfg = config()
    query = urlencode({
        "response_type": "code",
        "client_id": cfg.client_id,
        "scope": SCOPES,
        "state": state,
        "redirect_uri": cfg.redirect_uri,
    })
    return f"{cfg.base_url}/oauth/authorize?{query}"


async def _token_request(form: dict) -> dict:
    cfg = config()
    async with _client() as http:
        resp = await http.post(f"{cfg.base_url}/oauth/token", data=form,
                               headers={"Accept": "application/json"})
    payload: Any
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text}
    if resp.status_code >= 400:
        # HMRC returns {"error": "...", "error_description": "..."}
        message = (payload or {}).get("error_description") or f"HMRC token request failed ({resp.status_code})"
        raise HMRCError(resp.status_code, message, payload)
    return payload


async def exchange_code(code: str) -> dict:
    cfg = config()
    return await _token_request({
        "grant_type": "authorization_code",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "redirect_uri": cfg.redirect_uri,
        "code": code,
    })


async def refresh_tokens(refresh_token: str) -> dict:
    cfg = config()
    return await _token_request({
        "grant_type": "refresh_token",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "refresh_token": refresh_token,
    })


async def call(
    *,
    method: str,
    path: str,
    version: str,
    access_token: str,
    fraud_headers: dict,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
) -> tuple[int, Any, dict]:
    """One authenticated API call. Returns (status, payload, headers).

    Non-2xx is returned rather than raised: the caller records it in the
    audit trail before deciding what the user should see.
    """
    cfg = config()
    headers = {
        "Accept": f"application/vnd.hmrc.{version}+json",
        "Authorization": f"Bearer {access_token}",
        **fraud_headers,
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    async with _client() as http:
        resp = await http.request(method, f"{cfg.base_url}{path}",
                                  headers=headers, params=params, json=json_body)
    try:
        payload = resp.json() if resp.content else None
    except Exception:
        payload = {"raw": resp.text[:2000]}
    return resp.status_code, payload, dict(resp.headers)


# ---------------------------------------------------------------------------
# Endpoint paths. Kept together so a version bump is one obvious edit.
# ---------------------------------------------------------------------------

def path_list_businesses(nino: str) -> str:
    return f"/individuals/business/details/{nino}/list"


def path_obligations(nino: str) -> str:
    return f"/obligations/details/{nino}/income-and-expenditure"


def path_cumulative_summary(nino: str, business_id: str, tax_year: str) -> str:
    """Quarterly (cumulative year-to-date) update, tax year 2025-26 onward."""
    return f"/individuals/business/self-employment/{nino}/{business_id}/cumulative/{tax_year}"


def path_period_summary(nino: str, business_id: str) -> str:
    """The pre-2025-26 shape, kept for amending historic periods."""
    return f"/individuals/business/self-employment/{nino}/{business_id}/period"


def path_trigger_calculation(nino: str, tax_year: str, calculation_type: str = "in-year") -> str:
    return f"/individuals/calculations/{nino}/self-assessment/{tax_year}/trigger/{calculation_type}"


def path_retrieve_calculation(nino: str, tax_year: str, calculation_id: str) -> str:
    return f"/individuals/calculations/{nino}/self-assessment/{tax_year}/{calculation_id}"
