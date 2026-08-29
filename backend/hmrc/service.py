"""Orchestration: valid tokens, audited calls, business operations.

Every outbound call to HMRC is written to `asets.hmrc_submissions`
before it leaves and completed when the answer arrives, so the audit
trail records attempts as well as successes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from db import hmrc_repo, pool
from hmrc import client, mapping

logger = logging.getLogger("asets.hmrc")

# Refresh a little before expiry so a slow request cannot straddle it.
REFRESH_MARGIN = timedelta(seconds=90)


class NotConnected(Exception):
    pass


class GrantExpired(NotConnected):
    """The user's authorisation is no longer usable.

    HMRC grants last 18 months, and a user can revoke one at any time
    from their tax account. Either way the refresh stops working and the
    only cure is reconnecting — so this is surfaced as "not connected"
    rather than as a server error, which is what it would otherwise look
    like a year and a half after everything last worked.
    """


async def valid_access_token(user_id: str, connection: dict) -> str:
    """Return a usable access token, refreshing first if it is close to
    expiry.

    The new token pair is written in its own transaction. HMRC issues a
    fresh refresh token on every refresh and invalidates the old one, so
    if this write were part of the caller's transaction a later failure
    would roll it back and strand the connection permanently.
    """
    expires_at = connection["access_expires_at"]
    if expires_at and expires_at - REFRESH_MARGIN > datetime.now(timezone.utc):
        return connection["access_token"]

    logger.info("refreshing HMRC access token for %s", user_id)
    try:
        tokens = await client.refresh_tokens(connection["refresh_token"])
    except client.HMRCError as e:
        if _is_dead_grant(e):
            message = ("Your HMRC connection has expired or been withdrawn. "
                       "Reconnect in Settings → HMRC.")
            async with pool.tenant(user_id) as conn:
                await hmrc_repo.record_error(conn, user_id, message)
            logger.info("HMRC grant no longer valid for %s: %s", user_id, e.message)
            raise GrantExpired(message) from e
        raise
    async with pool.tenant(user_id) as conn:
        await hmrc_repo.update_tokens(conn, user_id, tokens)
    return tokens["access_token"]


def _is_dead_grant(error: client.HMRCError) -> bool:
    """Tell an expired/revoked grant apart from HMRC being unwell."""
    if error.status not in (400, 401, 403):
        return False
    payload = error.payload if isinstance(error.payload, dict) else {}
    return str(payload.get("error", "")).lower() in ("invalid_grant", "invalid_request")


async def require_connection(user_id: str) -> dict:
    async with pool.tenant(user_id) as conn:
        connection = await hmrc_repo.get_connection(conn, user_id)
    if connection is None:
        raise NotConnected("This account is not connected to HMRC yet.")
    return connection


async def audited_call(
    *,
    user_id: str,
    submission_type: str,
    method: str,
    path: str,
    version: str,
    access_token: str,
    fraud_headers: dict,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    tax_year: Optional[str] = None,
    business_id: Optional[str] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
) -> tuple[int, Any]:
    # Audit writes get their own transactions so the record survives a
    # rollback of whatever the caller is doing — a submission that failed
    # is precisely the one worth having a record of.
    async with pool.tenant(user_id) as audit:
        submission_id = await hmrc_repo.start_submission(
            audit, user_id=user_id, submission_type=submission_type,
            endpoint=f"{method} {path}", tax_year=tax_year, business_id=business_id,
            period_start=period_start, period_end=period_end, request_payload=json_body)

    try:
        status, payload, headers = await client.call(
            method=method, path=path, version=version, access_token=access_token,
            fraud_headers=fraud_headers, params=params, json_body=json_body)
    except Exception as e:
        async with pool.tenant(user_id) as audit:
            await hmrc_repo.complete_submission(audit, submission_id, status="error",
                                                response_payload={"transport_error": str(e)})
        raise

    outcome = "accepted" if 200 <= status < 300 else ("rejected" if status < 500 else "error")
    receipt = None
    if isinstance(payload, dict):
        receipt = payload.get("calculationId") or payload.get("receiptId")
    async with pool.tenant(user_id) as audit:
        await hmrc_repo.complete_submission(
            audit, submission_id, status=outcome, http_status=status,
            response_payload=payload if isinstance(payload, (dict, list)) else None,
            correlation_id=headers.get("x-correlationid") or headers.get("X-CorrelationId"),
            receipt_id=receipt)

    if outcome != "accepted":
        logger.warning("HMRC %s %s -> %s %s", method, path, status, payload)
    return status, payload


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

async def list_businesses(*, user_id: str, connection: dict, fraud_headers: dict) -> tuple[int, Any]:
    nino = connection.get("nino")
    if not nino:
        raise ValueError("A National Insurance number is needed before ASETS can find your business.")
    token = await valid_access_token(user_id, connection)
    return await audited_call(
        user_id=user_id, submission_type="retrieve_businesses",
        method="GET", path=client.path_list_businesses(nino),
        version=client.V_BUSINESS_DETAILS, access_token=token, fraud_headers=fraud_headers)


async def obligations(*, user_id: str, connection: dict, fraud_headers: dict,
                      tax_year: str, status_filter: Optional[str] = None) -> tuple[int, Any]:
    nino = connection.get("nino")
    if not nino:
        raise ValueError("A National Insurance number is needed to read your HMRC obligations.")
    start, end = mapping.tax_year_bounds(tax_year)
    params = {
        "typeOfBusiness": "self-employment",
        "fromDate": start.isoformat(),
        "toDate": end.isoformat(),
    }
    if connection.get("business_id"):
        params["businessId"] = connection["business_id"]
    if status_filter:
        params["status"] = status_filter

    token = await valid_access_token(user_id, connection)
    return await audited_call(
        user_id=user_id, submission_type="retrieve_obligations",
        method="GET", path=client.path_obligations(nino), version=client.V_OBLIGATIONS,
        access_token=token, fraud_headers=fraud_headers, params=params, tax_year=tax_year)


async def submit_cumulative(*, user_id: str, connection: dict, fraud_headers: dict,
                            tax_year: str, payload: dict) -> tuple[int, Any]:
    nino, business_id = connection.get("nino"), connection.get("business_id")
    if not nino or not business_id:
        raise ValueError("Connect your HMRC business before submitting an update.")
    token = await valid_access_token(user_id, connection)
    return await audited_call(
        user_id=user_id, submission_type="quarterly_update",
        method="PUT",
        path=client.path_cumulative_summary(nino, business_id, tax_year),
        version=client.V_SELF_EMPLOYMENT, access_token=token, fraud_headers=fraud_headers,
        json_body=payload, tax_year=tax_year, business_id=business_id,
        period_start=payload["periodDates"]["periodStartDate"],
        period_end=payload["periodDates"]["periodEndDate"])


async def trigger_calculation(*, user_id: str, connection: dict, fraud_headers: dict,
                              tax_year: str) -> tuple[int, Any]:
    nino = connection.get("nino")
    if not nino:
        raise ValueError("A National Insurance number is needed to run an HMRC calculation.")
    token = await valid_access_token(user_id, connection)
    return await audited_call(
        user_id=user_id, submission_type="trigger_calculation",
        method="POST", path=client.path_trigger_calculation(nino, tax_year),
        version=client.V_CALCULATIONS, access_token=token, fraud_headers=fraud_headers,
        tax_year=tax_year)


async def retrieve_calculation(*, user_id: str, connection: dict, fraud_headers: dict,
                               tax_year: str, calculation_id: str) -> tuple[int, Any]:
    nino = connection.get("nino")
    token = await valid_access_token(user_id, connection)
    return await audited_call(
        user_id=user_id, submission_type="retrieve_calculation",
        method="GET", path=client.path_retrieve_calculation(nino, tax_year, calculation_id),
        version=client.V_CALCULATIONS, access_token=token, fraud_headers=fraud_headers,
        tax_year=tax_year)
