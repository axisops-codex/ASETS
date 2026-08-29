"""Connection pool and per-request tenant scoping.

Every query the API makes runs inside a transaction that has first
declared *who is asking*:

    async with pool.tenant(user_id) as conn:
        rows = await conn.fetch("SELECT * FROM asets.invoices")

`tenant()` sets the `asets.user_id` setting, which every row-level
security policy checks. A query that forgets its WHERE clause therefore
returns the caller's rows, not everybody's — and a code path that forgets
to open a tenant scope at all returns nothing.

`anonymous()` is the deliberate escape hatch for the two operations that
happen before a tenant exists: registration and login.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import AsyncIterator, Optional

import asyncpg

logger = logging.getLogger("asets.db")

_pool: Optional[asyncpg.Pool] = None


def dsn() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


async def connect(url: Optional[str] = None, *, min_size: int = 1, max_size: int = 10,
                  attempts: int = 5, base_delay: float = 2.0) -> asyncpg.Pool:
    """Open the pool. Safe to call twice; the second call is a no-op.

    Retries with backoff: on a scale-to-zero platform the first request
    after an idle spell can arrive while the database is still waking, and
    a pooler that has just seen a credential change can reject one
    connection and accept the next. Failing the whole container for that
    would turn a two-second hiccup into an outage.
    """
    global _pool
    if _pool is not None:
        return _pool

    last: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            _pool = await _create(url, min_size, max_size)
            logger.info("database pool ready")
            return _pool
        except (asyncpg.PostgresError, OSError) as e:
            last = e
            if attempt == attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), 15)
            logger.warning("database not ready (%s: %s) — retrying in %ss",
                           type(e).__name__, e, delay)
            await asyncio.sleep(delay)
    raise RuntimeError(f"could not reach the database after {attempts} attempts: {last}")


async def _create(url: Optional[str], min_size: int, max_size: int) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        url or dsn(),
        min_size=min_size,
        max_size=max_size,
        # Cloud Run scales to zero and the Supabase pooler drops idle
        # connections; recycling keeps us from handing out a dead one.
        max_inactive_connection_lifetime=180.0,
        command_timeout=30.0,
        server_settings={"application_name": "asets-api", "search_path": "asets,public"},
    )


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("database pool is not initialised")
    return _pool


@contextlib.asynccontextmanager
async def tenant(user_id: str) -> AsyncIterator[asyncpg.Connection]:
    """A transaction scoped to one user. RLS does the rest."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('asets.user_id', $1, true)", str(user_id))
            yield conn


@contextlib.asynccontextmanager
async def anonymous() -> AsyncIterator[asyncpg.Connection]:
    """A transaction with no tenant: registration and login only.

    Tables under RLS are invisible here, which is exactly the intent —
    these two paths only ever touch `users`.
    """
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            yield conn


@contextlib.asynccontextmanager
async def privileged(user_id: str) -> AsyncIterator[asyncpg.Connection]:
    """Tenant scope plus permission to purge the HMRC audit trail.

    Used by account deletion only. The database refuses to delete an
    audit row unless this flag is set, so the capability is explicit and
    greppable rather than implied by holding a DELETE grant.
    """
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('asets.user_id', $1, true)", str(user_id))
            await conn.execute("SELECT set_config('asets.allow_audit_purge', 'on', true)")
            yield conn


async def healthy() -> bool:
    try:
        async with get_pool().acquire() as conn:
            return await conn.fetchval("SELECT 1") == 1
    except Exception as e:  # pragma: no cover - reported through /api/health
        logger.error(f"database health check failed: {e}")
        return False
