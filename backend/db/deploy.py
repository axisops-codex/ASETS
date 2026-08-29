#!/usr/bin/env python3
"""Deploy-time database step, run as a Cloud Run job before each release.

    python -m db.deploy

Reads:
    MIGRATION_DATABASE_URL  administrator DSN
    DB_APP_PASSWORD         password for the runtime role, asets_app
    DB_ROTATE_PASSWORD      set to 1 to reset that password (see below)

Ensures the runtime role exists, then applies any pending migrations.
Both steps are idempotent, so this runs on every deploy whether or not
anything has changed.

The password is set only when the role is created. Resetting it on every
deploy looked harmless but is not: connection poolers cache credentials,
so a routine deploy would leave the API unable to authenticate for the
minutes it takes the cache to catch up. Rotating is now deliberate —
update the secret, then run once with DB_ROTATE_PASSWORD=1.
"""
import asyncio
import os
import sys

import asyncpg

from db import migrate


async def ensure_app_role(url: str, password: str, rotate: bool) -> None:
    conn = await asyncpg.connect(url)
    try:
        ident = await conn.fetchval("SELECT quote_ident('asets_app')")
        literal = await conn.fetchval("SELECT quote_literal($1)", password)
        if await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = 'asets_app'"):
            if rotate:
                await conn.execute(f"ALTER ROLE {ident} WITH LOGIN PASSWORD {literal}")
                print("✓ rotated the asets_app password "
                      "(pooled connections may fail to authenticate for a minute)")
            else:
                print("· role asets_app present (password left alone)")
        else:
            await conn.execute(f"CREATE ROLE {ident} LOGIN PASSWORD {literal}")
            print("✓ created role asets_app")
    finally:
        await conn.close()


async def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        print("MIGRATION_DATABASE_URL is not set", file=sys.stderr)
        return 2

    password = os.environ.get("DB_APP_PASSWORD", "")
    rotate = os.environ.get("DB_ROTATE_PASSWORD", "") in ("1", "true", "yes")
    if password:
        await ensure_app_role(url, password, rotate)
    else:
        print("· DB_APP_PASSWORD not set — leaving the runtime role alone")

    return await migrate.run(url)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
