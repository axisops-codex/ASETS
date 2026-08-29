"""Test harness.

Each test session runs against a real PostgreSQL cluster — not a mock,
not SQLite. Row-level security, check constraints, triggers and the
generated columns are most of this application's correctness, and none of
them can be exercised against a substitute.

The cluster is created in a temporary directory, migrated, and thrown
away afterwards. Under xdist each worker gets its own cluster and port,
so tests stay isolated and can run in parallel.

Set TEST_DATABASE_URL to point at an existing database instead (it must
be superuser-capable: the harness creates roles).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# The live suite talks to a deployed server; it is opt-in.
collect_ignore_glob = [] if os.environ.get("ASETS_LIVE_TESTS") else ["live/*"]

PG_BIN_CANDIDATES = [
    os.environ.get("PG_BIN", ""),
    "/opt/homebrew/opt/postgresql@17/bin",
    "/opt/homebrew/opt/postgresql@16/bin",
    "/usr/lib/postgresql/17/bin",
    "/usr/lib/postgresql/16/bin",
    "/usr/local/opt/postgresql@17/bin",
]


def _pg_bin() -> Path:
    for candidate in PG_BIN_CANDIDATES:
        if candidate and (Path(candidate) / "initdb").exists():
            return Path(candidate)
    found = shutil.which("initdb")
    if found:
        return Path(found).parent
    pytest.skip("PostgreSQL binaries not found — set PG_BIN or install postgresql@17")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def pg_cluster():
    """A throwaway PostgreSQL cluster, one per xdist worker."""
    if os.environ.get("TEST_DATABASE_URL"):
        yield os.environ["TEST_DATABASE_URL"]
        return

    pg_bin = _pg_bin()
    workdir = Path(tempfile.mkdtemp(prefix="asets-pg-"))
    datadir = workdir / "data"
    port = _free_port()

    subprocess.run([str(pg_bin / "initdb"), "-D", str(datadir), "-U", "postgres",
                    "--auth=trust", "-E", "UTF8", "--locale=C"],
                   check=True, capture_output=True)
    # -k /tmp keeps the socket path inside macOS's 103-byte limit.
    subprocess.run([str(pg_bin / "pg_ctl"), "-D", str(datadir), "-w", "-l",
                    str(workdir / "pg.log"), "-o",
                    f"-p {port} -k /tmp -c listen_addresses=127.0.0.1 -c fsync=off",
                    "start"],
                   check=True, capture_output=True)
    try:
        env = {**os.environ, "PGHOST": "127.0.0.1", "PGPORT": str(port), "PGUSER": "postgres"}
        subprocess.run([str(pg_bin / "createdb"), "asets_test"], check=True, env=env, capture_output=True)
        subprocess.run([str(pg_bin / "psql"), "-d", "asets_test", "-v", "ON_ERROR_STOP=1", "-c",
                        "CREATE ROLE asets_app LOGIN PASSWORD 'testpw'"],
                       check=True, env=env, capture_output=True)
        yield f"postgresql://postgres@127.0.0.1:{port}/asets_test"
    finally:
        subprocess.run([str(pg_bin / "pg_ctl"), "-D", str(datadir), "-m", "immediate", "stop"],
                       capture_output=True)
        shutil.rmtree(workdir, ignore_errors=True)


@pytest.fixture(scope="session")
def superuser_url(pg_cluster) -> str:
    """Superuser DSN — migrations and direct schema assertions."""
    from db import migrate
    assert asyncio.run(migrate.run(pg_cluster)) == 0
    return pg_cluster


@pytest.fixture(scope="session")
def app_url(superuser_url) -> str:
    """The DSN the application uses: the unprivileged, RLS-bound role."""
    return superuser_url.replace("postgresql://postgres@", "postgresql://asets_app:testpw@")


@pytest.fixture(scope="session", autouse=True)
def _environment(app_url):
    """Environment the app reads at import time."""
    import crypto

    # server.py calls load_dotenv(backend/.env), and python-dotenv does not
    # override what is already set — so anything the developer happens to
    # have configured locally would leak in and change how the suite
    # behaves. Pin the optional integrations to "off" so a test asserting
    # "this feature is unavailable" means the same thing on every machine.
    for name in ("ANTHROPIC_API_KEY", "EMERGENT_LLM_KEY", "EMERGENT_EMAIL_KEY",
                 "COMPANIES_HOUSE_API_KEY", "LLM_PROVIDER"):
        os.environ[name] = ""

    os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
    os.environ["DATABASE_URL"] = app_url
    os.environ["TOKEN_ENCRYPTION_KEY"] = crypto.generate_key()
    os.environ["HMRC_CLIENT_ID"] = "test-client-id"
    os.environ["HMRC_CLIENT_SECRET"] = "test-client-secret"
    os.environ["HMRC_REDIRECT_URI"] = "https://api.test/api/hmrc/callback"
    os.environ["HMRC_ENVIRONMENT"] = "sandbox"
    os.environ["HMRC_VENDOR_PUBLIC_IP"] = "203.0.113.6"
    yield


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def db_pool(app_url):
    from db import pool
    await pool.connect(app_url, max_size=5)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(loop_scope="session")
async def api(db_pool):
    """An HTTP client bound to the ASGI app (no network, no server)."""
    import httpx
    import server
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        yield client


@pytest_asyncio.fixture(loop_scope="session")
async def clean_db(db_pool, superuser_url):
    """Empty every tenant table between tests, as superuser."""
    import asyncpg
    conn = await asyncpg.connect(superuser_url)
    try:
        async with conn.transaction():
            # Transaction-scoped, exactly as the application sets it — a
            # session-level SET would leak across pooled connections.
            await conn.execute("SELECT set_config('asets.allow_audit_purge','on',true)")
            await conn.execute("TRUNCATE asets.users CASCADE")
    finally:
        await conn.close()
    yield


import uuid as _uuid


@pytest_asyncio.fixture(loop_scope="session")
async def user(api, clean_db) -> dict:
    """A registered user plus an authorised client-side header set."""
    email = f"a_{_uuid.uuid4().hex[:10]}@example.com"
    resp = await api.post("/api/auth/register",
                          json={"email": email, "password": "secret123", "name": "Dr A"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return {"email": email, "password": "secret123", "token": data["access_token"],
            "id": data["user"]["id"],
            "headers": {"Authorization": f"Bearer {data['access_token']}"}}


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(api, user) -> dict:
    """A second tenant, for isolation tests. Depends on `user` so the
    database is cleaned once, not twice."""
    email = f"b_{_uuid.uuid4().hex[:10]}@example.com"
    resp = await api.post("/api/auth/register",
                          json={"email": email, "password": "secret123", "name": "Dr B"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return {"email": email, "token": data["access_token"], "id": data["user"]["id"],
            "headers": {"Authorization": f"Bearer {data['access_token']}"}}
