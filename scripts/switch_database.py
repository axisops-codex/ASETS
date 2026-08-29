#!/usr/bin/env python3
"""Point ASETS at a different PostgreSQL database, end to end.

    python3 scripts/switch_database.py --supabase-ref bmxytncvoancaakryjkw

Takes the new project's database administrator password from
SUPABASE_DB_PASSWORD (environment or backend/.env), or prompts for it —
never echoed, and never passed on the command line where it would land in
shell history. Then:

  1. finds the right Supabase pooler host for that project,
  2. creates the asets_app role and applies every migration,
  3. checks the application role can actually connect and that row-level
     security is switched on,
  4. rewrites DATABASE_URL / MIGRATION_DATABASE_URL in backend/.env,
  5. updates the same secrets in GCP Secret Manager,
  6. redeploys Cloud Run and waits for a healthy response.

Any step can be skipped with --no-gcp / --no-deploy. Re-running is safe.
SUPABASE_DB_PASSWORD is removed from backend/.env once the switch
succeeds — it is the administrator credential and the application never
needs it.

Moving existing data is a separate, deliberate step — see LAUNCH.md §2.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ENV_FILE = BACKEND / ".env"
sys.path.insert(0, str(BACKEND))

import asyncpg  # noqa: E402

# Supabase has more than one pooler fleet; which one a project is on
# depends on when it was created, so probe rather than assume.
HOST_PREFIXES = ("aws-1", "aws-0")
REGIONS = ("eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1",
           "us-east-1", "us-east-2", "us-west-1", "ap-southeast-1", "ap-south-1")

ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def note(msg: str) -> None:
    print(f"\033[1m▸ {msg}\033[0m")


def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def warn(msg: str) -> None:
    print(f"  \033[33m!\033[0m {msg}")


async def find_pooler(ref: str, password: str, region: str | None) -> str:
    """The pooler host that knows this project.

    A wrong host answers 'tenant not found'; the right one answers about
    the password, which is how we tell them apart.
    """
    regions = [region] if region else list(REGIONS)
    for prefix in HOST_PREFIXES:
        for candidate in regions:
            host = f"{prefix}-{candidate}.pooler.supabase.com"
            dsn = f"postgresql://postgres.{ref}:{password}@{host}:5432/postgres?sslmode=require"
            try:
                conn = await asyncio.wait_for(asyncpg.connect(dsn), 12)
                await conn.close()
                ok(f"{host} (password accepted)")
                return host
            except asyncpg.InvalidPasswordError:
                raise SystemExit(
                    f"\n  Found the project on {host}, but that password was rejected.\n"
                    f"  Reset it in the Supabase dashboard: Project Settings → Database →\n"
                    f"  Database password → Reset, then run this again.")
            except (asyncio.TimeoutError, OSError):
                continue
            except Exception as e:
                if "not found" in str(e).lower():
                    continue
                raise
    raise SystemExit(f"Could not find a pooler host for project {ref}. "
                     f"Check the project reference.")


async def verify(app_dsn: str) -> None:
    conn = await asyncpg.connect(app_dsn)
    try:
        who = await conn.fetchval("SELECT current_user")
        tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'asets'")
        # Every tenant table must refuse to answer without a tenant set.
        leaked = await conn.fetchval("SELECT count(*) FROM asets.clients")
        forced = await conn.fetchval(
            """SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'asets' AND c.relrowsecurity AND c.relforcerowsecurity""")
    finally:
        await conn.close()
    ok(f"connects as {who}, sees {tables} tables in schema asets")
    ok(f"row-level security forced on {forced} tables")
    if leaked:
        raise SystemExit("  ✗ rows were visible without a tenant — RLS is not doing its job")
    ok("no rows visible without a tenant (default deny)")


def load_env() -> dict:
    env = dict(os.environ)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
            if m and not env.get(m.group(1)):
                env[m.group(1)] = m.group(2)
    return env


def rewrite_env(app_dsn: str, migration_dsn: str, app_password: str) -> None:
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    # The administrator password was only needed to build the schema.
    text = re.sub(r"^SUPABASE_DB_PASSWORD=.*\n?", "", text, flags=re.M)
    for key, value in (("DATABASE_URL", app_dsn),
                       ("MIGRATION_DATABASE_URL", migration_dsn),
                       ("DB_APP_PASSWORD", app_password)):
        line = f"{key}={value}"
        if re.search(rf"^{key}=", text, flags=re.M):
            text = re.sub(rf"^{key}=.*$", line, text, flags=re.M)
        else:
            text += ("\n" if text and not text.endswith("\n") else "") + line + "\n"
    ENV_FILE.write_text(text)
    os.chmod(ENV_FILE, 0o600)
    ok(f"updated {ENV_FILE.relative_to(ROOT)}")


def push_secret(project: str, name: str, value: str) -> None:
    exists = subprocess.run(["gcloud", "secrets", "describe", name, f"--project={project}"],
                            capture_output=True).returncode == 0
    if not exists:
        subprocess.run(["gcloud", "secrets", "create", name, "--replication-policy=automatic",
                        f"--project={project}"], check=True, capture_output=True)
    subprocess.run(["gcloud", "secrets", "versions", "add", name, "--data-file=-",
                    f"--project={project}"], input=value.encode(), check=True, capture_output=True)
    ok(name)


def gcp_project() -> str | None:
    env_out = ROOT / "deploy" / "gcp.env"
    if not env_out.exists():
        return None
    for line in env_out.read_text().splitlines():
        if line.startswith("PROJECT_ID="):
            return line.split("=", 1)[1].strip()
    return None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--supabase-ref", required=True, help="the project reference")
    ap.add_argument("--region", help="skip probing and use this region")
    ap.add_argument("--no-gcp", action="store_true", help="do not touch Secret Manager")
    ap.add_argument("--no-deploy", action="store_true", help="do not redeploy Cloud Run")
    args = ap.parse_args()

    ref = args.supabase_ref
    admin_password = load_env().get("SUPABASE_DB_PASSWORD", "").strip()
    if admin_password:
        ok("using SUPABASE_DB_PASSWORD")
    else:
        admin_password = getpass.getpass("Supabase database password (not echoed): ").strip()
    if not admin_password:
        raise SystemExit("No password given.")

    note(f"Finding the pooler for {ref}")
    host = await find_pooler(ref, admin_password, args.region)

    migration_dsn = (f"postgresql://postgres.{ref}:{admin_password}"
                     f"@{host}:5432/postgres?sslmode=require")
    app_password = "".join(secrets.choice(ALPHABET) for _ in range(32))
    app_dsn = (f"postgresql://asets_app.{ref}:{app_password}"
               f"@{host}:5432/postgres?sslmode=require")

    note("Creating the application role and applying migrations")
    from db import deploy as db_deploy
    os.environ["MIGRATION_DATABASE_URL"] = migration_dsn
    os.environ["DB_APP_PASSWORD"] = app_password
    os.environ["DB_ROTATE_PASSWORD"] = "1"     # first time on this database
    if await db_deploy.main() != 0:
        return 1

    note("Checking the application role")
    # The pooler caches credentials for a moment after a role changes.
    for attempt in range(6):
        try:
            await verify(app_dsn)
            break
        except asyncpg.InvalidPasswordError:
            if attempt == 5:
                raise
            await asyncio.sleep(5)

    note("Recording the new connection")
    rewrite_env(app_dsn, migration_dsn, app_password)

    project = gcp_project()
    if args.no_gcp or not project:
        warn("skipped Secret Manager" if args.no_gcp else "no deploy/gcp.env — skipped GCP")
    else:
        note(f"Updating secrets in {project}")
        push_secret(project, "DATABASE_URL", app_dsn)
        push_secret(project, "MIGRATION_DATABASE_URL", migration_dsn)
        push_secret(project, "DB_APP_PASSWORD", app_password)

        if not args.no_deploy:
            note("Redeploying Cloud Run")
            subprocess.run([str(ROOT / "scripts" / "deploy_cloudrun.sh")], check=True)

    print("\nDone. The old database still has its copy of the schema; remove it with:")
    print("  DROP SCHEMA asets CASCADE; DROP ROLE asets_app; DROP ROLE asets_migrate;")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
