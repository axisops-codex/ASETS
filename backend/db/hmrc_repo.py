"""Persistence for the HMRC connection and its audit trail."""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg

import crypto


# ---------------------------------------------------------------------------
# OAuth handshake
# ---------------------------------------------------------------------------

async def create_oauth_state(conn: asyncpg.Connection, user_id: str, redirect_uri: str,
                             ttl_minutes: int = 15) -> str:
    state = secrets.token_urlsafe(32)
    await conn.execute(
        """INSERT INTO asets.hmrc_oauth_states (state, user_id, code_verifier, redirect_uri, expires_at)
           VALUES ($1, $2, $3, $4, now() + ($5 || ' minutes')::interval)""",
        state, user_id, secrets.token_urlsafe(32), redirect_uri, str(ttl_minutes))
    return state


async def consume_oauth_state(conn: asyncpg.Connection, state: str) -> Optional[dict]:
    """Single use, and only inside its window. Returns None otherwise."""
    row = await conn.fetchrow(
        """UPDATE asets.hmrc_oauth_states
              SET used_at = now()
            WHERE state = $1 AND used_at IS NULL AND expires_at > now()
        RETURNING user_id, redirect_uri""",
        state)
    if row is None:
        return None
    return {"user_id": str(row["user_id"]), "redirect_uri": row["redirect_uri"]}


async def purge_expired_states(conn: asyncpg.Connection) -> int:
    return int((await conn.execute(
        "DELETE FROM asets.hmrc_oauth_states WHERE expires_at < now() - interval '1 day'"
    )).split()[-1])


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _expiry(expires_in: Any) -> datetime:
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        seconds = 3600
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


async def save_tokens(conn: asyncpg.Connection, user_id: str, tokens: dict,
                      environment: str) -> None:
    await conn.execute(
        """INSERT INTO asets.hmrc_connections
             (user_id, access_token, refresh_token, access_expires_at, scopes, environment)
           VALUES ($1, $2, $3, $4, $5, $6)
           ON CONFLICT (user_id) DO UPDATE SET
             access_token = EXCLUDED.access_token,
             refresh_token = EXCLUDED.refresh_token,
             access_expires_at = EXCLUDED.access_expires_at,
             scopes = EXCLUDED.scopes,
             environment = EXCLUDED.environment,
             last_error = NULL""",
        user_id,
        crypto.encrypt(tokens["access_token"]),
        crypto.encrypt(tokens["refresh_token"]),
        _expiry(tokens.get("expires_in")),
        (tokens.get("scope") or "").split(),
        environment)


async def get_connection(conn: asyncpg.Connection, user_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        """SELECT nino_encrypted, business_id, business_type, accounting_type,
                  access_token, refresh_token, access_expires_at, scopes,
                  environment, connected_at, updated_at, last_error
             FROM asets.hmrc_connections WHERE user_id = $1""",
        user_id)
    if row is None:
        return None
    return {
        "nino": crypto.decrypt_optional(row["nino_encrypted"]),
        "business_id": row["business_id"],
        "business_type": row["business_type"],
        "accounting_type": row["accounting_type"],
        "access_token": crypto.decrypt(row["access_token"]),
        "refresh_token": crypto.decrypt(row["refresh_token"]),
        "access_expires_at": row["access_expires_at"],
        "scopes": list(row["scopes"] or []),
        "environment": row["environment"],
        "connected_at": row["connected_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "last_error": row["last_error"],
    }


async def update_tokens(conn: asyncpg.Connection, user_id: str, tokens: dict) -> None:
    await conn.execute(
        """UPDATE asets.hmrc_connections
              SET access_token = $2, refresh_token = $3, access_expires_at = $4, last_error = NULL
            WHERE user_id = $1""",
        user_id, crypto.encrypt(tokens["access_token"]),
        crypto.encrypt(tokens["refresh_token"]), _expiry(tokens.get("expires_in")))


async def set_business(conn: asyncpg.Connection, user_id: str, *, nino: Optional[str] = None,
                       business_id: Optional[str] = None, business_type: Optional[str] = None) -> None:
    await conn.execute(
        """UPDATE asets.hmrc_connections
              SET nino_encrypted = COALESCE($2, nino_encrypted),
                  business_id    = COALESCE($3, business_id),
                  business_type  = COALESCE($4, business_type)
            WHERE user_id = $1""",
        user_id, crypto.encrypt_optional(nino), business_id, business_type)


async def record_error(conn: asyncpg.Connection, user_id: str, message: str) -> None:
    await conn.execute(
        "UPDATE asets.hmrc_connections SET last_error = $2 WHERE user_id = $1",
        user_id, message[:500])


async def disconnect(conn: asyncpg.Connection, user_id: str) -> None:
    await conn.execute("DELETE FROM asets.hmrc_connections WHERE user_id = $1", user_id)


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def _as_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


async def start_submission(conn: asyncpg.Connection, *, user_id: str, submission_type: str,
                           endpoint: str, tax_year: Optional[str] = None,
                           business_id: Optional[str] = None,
                           period_start=None, period_end=None,
                           request_payload: Optional[dict] = None) -> str:
    row = await conn.fetchrow(
        """INSERT INTO asets.hmrc_submissions
             (user_id, submission_type, endpoint, tax_year, business_id,
              period_start, period_end, request_payload)
           VALUES ($1, $2::asets.hmrc_submission_type, $3, $4, $5, $6, $7, $8::jsonb)
           RETURNING id""",
        user_id, submission_type, endpoint, tax_year, business_id,
        _as_date(period_start), _as_date(period_end),
        json.dumps(request_payload) if request_payload is not None else None)
    return str(row["id"])


async def complete_submission(conn: asyncpg.Connection, submission_id: str, *, status: str,
                              http_status: Optional[int] = None,
                              response_payload: Any = None,
                              correlation_id: Optional[str] = None,
                              receipt_id: Optional[str] = None) -> None:
    """A submission row may be completed exactly once — the database
    trigger rejects any later change."""
    await conn.execute(
        """UPDATE asets.hmrc_submissions
              SET status = $2::asets.hmrc_submission_status,
                  http_status = $3,
                  response_payload = $4::jsonb,
                  correlation_id = $5,
                  receipt_id = $6,
                  completed_at = now()
            WHERE id = $1""",
        submission_id, status, http_status,
        json.dumps(response_payload) if response_payload is not None else None,
        correlation_id, receipt_id)


async def list_submissions(conn: asyncpg.Connection, limit: int = 50) -> list:
    rows = await conn.fetch(
        """SELECT id, submission_type, status, tax_year, period_start, period_end,
                  endpoint, http_status, receipt_id, correlation_id, created_at, completed_at
             FROM asets.hmrc_submissions
            ORDER BY created_at DESC LIMIT $1""", limit)
    return [{
        "id": str(r["id"]),
        "type": r["submission_type"],
        "status": r["status"],
        "tax_year": r["tax_year"],
        "period_start": r["period_start"].isoformat() if r["period_start"] else None,
        "period_end": r["period_end"].isoformat() if r["period_end"] else None,
        "endpoint": r["endpoint"],
        "http_status": r["http_status"],
        "receipt_id": r["receipt_id"],
        "correlation_id": r["correlation_id"],
        "created_at": r["created_at"].isoformat(),
        "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
    } for r in rows]
