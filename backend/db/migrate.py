#!/usr/bin/env python3
"""Apply the SQL migrations in backend/db/migrations, in order, once.

    python -m db.migrate                 # uses DATABASE_URL
    python -m db.migrate --dry-run       # show what would run
    python -m db.migrate --url postgres://...

Each file runs inside its own transaction: a failure leaves the database
on the previous migration rather than half-way through this one. Applied
files are fingerprinted, so editing a migration that has already run is
an error rather than a silent divergence between environments.
"""
import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

BOOTSTRAP = """
CREATE SCHEMA IF NOT EXISTS asets;
CREATE TABLE IF NOT EXISTS asets.schema_migrations (
    version     text PRIMARY KEY,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    duration_ms integer NOT NULL
);
"""


def discover():
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(f"no migrations found in {MIGRATIONS_DIR}")
    return [(f.stem, f, hashlib.sha256(f.read_bytes()).hexdigest()) for f in files]


async def run(url: str, dry_run: bool = False) -> int:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(BOOTSTRAP)
        applied = {r["version"]: r["checksum"] for r in
                   await conn.fetch("SELECT version, checksum FROM asets.schema_migrations")}

        pending = []
        for version, path, checksum in discover():
            if version in applied:
                if applied[version] != checksum:
                    print(f"✗ {version} was applied but its file has changed since.\n"
                          f"  Migrations are immutable — add a new one instead.", file=sys.stderr)
                    return 1
                continue
            pending.append((version, path, checksum))

        if not pending:
            print(f"✓ database is up to date ({len(applied)} migrations applied)")
            return 0

        for version, path, checksum in pending:
            if dry_run:
                print(f"→ would apply {version}")
                continue
            sql = path.read_text()
            start = asyncio.get_running_loop().time()
            async with conn.transaction():
                await conn.execute(sql)
                ms = int((asyncio.get_running_loop().time() - start) * 1000)
                await conn.execute(
                    "INSERT INTO asets.schema_migrations (version, checksum, duration_ms) VALUES ($1, $2, $3)",
                    version, checksum, ms)
            print(f"✓ applied {version} ({ms} ms)")
        return 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.url:
        print("DATABASE_URL is not set (and --url was not given)", file=sys.stderr)
        return 2
    return asyncio.run(run(args.url, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
