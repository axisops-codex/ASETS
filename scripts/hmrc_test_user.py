#!/usr/bin/env python3
"""Create an HMRC sandbox test user for walking the MTD flow.

    python3 scripts/hmrc_test_user.py

Sandbox only, by construction: the credentials in backend/.env are
sandbox credentials and this refuses to run against production, where
there is no such thing as a test user.

Needs the application to be subscribed to the **Create Test User** API
(Developer Hub → your application → API subscriptions). If it is not,
this says so rather than failing obscurely.

The result is written to hmrc-test-user.json, which is git-ignored: it
contains Government Gateway credentials, and although they are fake they
are still credentials.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hmrc-test-user.json"
SANDBOX = "https://test-api.service.hmrc.gov.uk"

# Everything ASETS touches. mtd-income-tax is the one that matters;
# the others make the user usable for wider testing later.
SERVICES = ["mtd-income-tax", "self-assessment", "national-insurance"]


def load_env() -> dict:
    env = dict(os.environ)
    env_file = ROOT / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
            if m and not env.get(m.group(1)):
                env[m.group(1)] = m.group(2)
    return env


async def main() -> int:
    env = load_env()
    cid = env.get("HMRC_CLIENT_ID", "").strip()
    secret = env.get("HMRC_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        print("HMRC_CLIENT_ID / HMRC_CLIENT_SECRET are not set in backend/.env", file=sys.stderr)
        return 2
    if (env.get("HMRC_ENVIRONMENT") or "sandbox").lower() != "sandbox":
        print("HMRC_ENVIRONMENT is not sandbox — test users only exist in the sandbox.",
              file=sys.stderr)
        return 2

    async with httpx.AsyncClient(timeout=60) as http:
        token = await http.post(f"{SANDBOX}/oauth/token",
                                data={"grant_type": "client_credentials",
                                      "client_id": cid, "client_secret": secret})
        if token.status_code != 200:
            print(f"Could not get an application token: {token.text[:200]}", file=sys.stderr)
            return 1
        access = token.json()["access_token"]

        resp = await http.post(f"{SANDBOX}/create-test-user/individuals",
                               headers={"Accept": "application/vnd.hmrc.1.0+json",
                                        "Authorization": f"Bearer {access}",
                                        "Content-Type": "application/json"},
                               json={"serviceNames": SERVICES})

    if resp.status_code >= 300:
        try:
            code = resp.json().get("code", "")
        except Exception:
            code = ""
        if code == "RESOURCE_FORBIDDEN":
            print("The application is not subscribed to the Create Test User API.\n\n"
                  "  Developer Hub → your application → API subscriptions →\n"
                  "  find 'Create Test User' → subscribe (sandbox is immediate).\n\n"
                  "Then run this again.", file=sys.stderr)
        else:
            print(f"HTTP {resp.status_code}: {resp.text[:400]}", file=sys.stderr)
        return 1

    user = resp.json()
    OUT.write_text(json.dumps(user, indent=2))
    os.chmod(OUT, 0o600)

    details = user.get("individualDetails") or {}
    print("Sandbox test user created — these are fake credentials for HMRC's test service.\n")
    print(f"  Government Gateway ID   {user.get('userId')}")
    print(f"  Password                {user.get('password')}")
    print(f"  National Insurance no   {user.get('nino')}")
    print(f"  MTD Income Tax ID       {user.get('mtdItId')}")
    print(f"  Self Assessment UTR     {user.get('saUtr')}")
    print(f"  Name                    {details.get('firstName','')} {details.get('lastName','')}")
    print(f"\n  Saved to {OUT.name} (git-ignored, mode 600)\n")
    print("In the app: Settings → HMRC → Connect to HMRC, sign in with the Government\n"
          "Gateway ID and password above, then enter that National Insurance number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
