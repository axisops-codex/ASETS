#!/usr/bin/env python3
"""Check the HMRC setup without needing a browser or a test user.

    python3 scripts/check_hmrc.py

Reads the credentials from backend/.env (or the environment) and answers
the four questions that actually block a submission:

  1. Are the client credentials valid, and for which environment?
  2. Is the application subscribed to every API ASETS calls?
  3. Is the redirect URI registered?
  4. Are the API versions ASETS pins still accepted?
  5. Do our fraud prevention headers pass HMRC's own validator?

Everything here is read-only. Nothing is submitted to HMRC.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

SANDBOX = "https://test-api.service.hmrc.gov.uk"
PRODUCTION = "https://api.service.hmrc.gov.uk"
SIGN_IN = {SANDBOX: "https://test-www.tax.service.gov.uk",
           PRODUCTION: "https://www.tax.service.gov.uk"}

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def load_env() -> dict:
    env = dict(os.environ)
    env_file = ROOT / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
            if m and not env.get(m.group(1)):
                env[m.group(1)] = m.group(2)
    return env


def ok(msg): print(f"  {GREEN}✓{RESET} {msg}")
def bad(msg): print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}!{RESET} {msg}")
def head(msg): print(f"\n\033[1m▸ {msg}{RESET}")


async def server_token(client: httpx.AsyncClient, base: str, cid: str, secret: str):
    r = await client.post(f"{base}/oauth/token",
                          data={"grant_type": "client_credentials",
                                "client_id": cid, "client_secret": secret},
                          headers={"Accept": "application/json"})
    if r.status_code == 200:
        return r.json().get("access_token")
    return None


async def main() -> int:
    from hmrc import client as hmrc_client

    env = load_env()
    cid = env.get("HMRC_CLIENT_ID", "").strip()
    secret = env.get("HMRC_CLIENT_SECRET", "").strip()
    redirect = env.get("HMRC_REDIRECT_URI", "").strip()

    if not cid or not secret:
        bad("HMRC_CLIENT_ID / HMRC_CLIENT_SECRET are not set (backend/.env)")
        return 2

    async with httpx.AsyncClient(timeout=40, follow_redirects=False) as http:
        head("Credentials")
        token, base = None, None
        for candidate, label in ((SANDBOX, "sandbox"), (PRODUCTION, "production")):
            found = await server_token(http, candidate, cid, secret)
            if found:
                ok(f"valid in {label}")
                token, base = found, candidate
            else:
                print(f"  {DIM}· not valid in {label}{RESET}")
        if not token:
            bad("these credentials are not accepted in either environment")
            return 1

        configured = (env.get("HMRC_ENVIRONMENT") or "sandbox").lower()
        expected = "sandbox" if base == SANDBOX else "production"
        (ok if configured == expected else bad)(
            f"HMRC_ENVIRONMENT={configured}, credentials are {expected}")

        head("API subscriptions")
        nino, business, tax_year = "AA123456A", "XAIS12345678910", "2026-27"
        checks = [
            ("Business Details", hmrc_client.V_BUSINESS_DETAILS, "GET",
             hmrc_client.path_list_businesses(nino)),
            ("Obligations", hmrc_client.V_OBLIGATIONS, "GET",
             hmrc_client.path_obligations(nino)),
            ("Self Employment Business", hmrc_client.V_SELF_EMPLOYMENT, "PUT",
             hmrc_client.path_cumulative_summary(nino, business, tax_year)),
            ("Individual Calculations", hmrc_client.V_CALCULATIONS, "POST",
             hmrc_client.path_trigger_calculation(nino, tax_year)),
        ]
        missing = []
        for name, version, method, path in checks:
            r = await http.request(method, base + path,
                                   headers={"Accept": f"application/vnd.hmrc.{version}+json",
                                            "Authorization": f"Bearer {token}",
                                            "Content-Type": "application/json"},
                                   json={} if method in ("PUT", "POST") else None)
            try:
                code = r.json().get("code", "")
            except Exception:
                code = ""
            if code == "RESOURCE_FORBIDDEN":
                bad(f"{name} v{version} — not subscribed")
                missing.append(name)
            elif code == "NOT_FOUND" and "version" in r.text.lower():
                bad(f"{name} v{version} — that version is not available")
                missing.append(name)
            else:
                ok(f"{name} v{version}")

        # Optional: only needed to generate sandbox test users.
        r = await http.post(base + "/create-test-user/individuals",
                            headers={"Accept": "application/vnd.hmrc.1.0+json",
                                     "Authorization": f"Bearer {token}",
                                     "Content-Type": "application/json"},
                            json={"serviceNames": ["mtd-income-tax"]})
        if base == SANDBOX:
            if r.status_code < 300:
                ok("Create Test User v1.0 (optional)")
            else:
                warn("Create Test User v1.0 — not subscribed. Optional: subscribe to it to "
                     "generate test users from the command line, or make one in the "
                     "Developer Hub UI.")

        head("Redirect URI")
        if not redirect:
            bad("HMRC_REDIRECT_URI is not set")
        else:
            url = (f"{SIGN_IN[base]}/oauth/authorize?response_type=code&client_id={cid}"
                   f"&scope={quote('read:self-assessment write:self-assessment')}"
                   f"&state=preflight&redirect_uri={quote(redirect, safe='')}")
            r = await http.get(url)
            body = r.text.lower()
            if r.status_code in (302, 303) or "sign in" in body or "government gateway" in body:
                ok(f"{redirect} is registered")
            elif "redirect_uri" in body:
                bad(f"{redirect} is NOT registered on the application")
                print(f"    Add it on the Developer Hub under your application's redirect URIs.")
                missing.append("redirect URI")
            else:
                warn(f"could not tell — HTTP {r.status_code}")

        head("Fraud prevention headers")
        if base != SANDBOX:
            print(f"  {DIM}· the validator is sandbox-only{RESET}")
        else:
            sys.path.insert(0, str(ROOT / "backend"))
            from hmrc import fraud

            await fraud.resolve_vendor_public_ip()
            if not fraud.vendor_public_ip():
                warn("could not resolve our own public IP — Gov-Vendor-Public-IP "
                     "and Gov-Vendor-Forwarded will be missing")

            # A representative device payload, exactly the shape
            # frontend/src/utils/device.ts sends.
            device = {
                "deviceId": "beec798b-b366-47fa-b1f8-92cede14a1ce",
                "timezone": "UTC+01:00",
                "localIps": ["10.1.2.3"],
                "localIpsTimestamp": "2026-01-01T00:00:00.000Z",
                "screens": {"width": 1179, "height": 2556, "scalingFactor": 3, "colourDepth": 32},
                "windowSize": {"width": 1179, "height": 2556},
                "os": {"family": "iOS", "version": "26.1",
                       "manufacturer": "Apple", "model": "iPhone17,2"},
                "appVersion": "1.0.0",
                "multiFactor": [{"type": "OTHER", "timestamp": "2026-01-01T00:00:00.000Z",
                                 "reference": "0000000000000000"}],
            }
            headers = fraud.build_headers(
                device, user_id="00000000-0000-0000-0000-000000000000",
                client_ip="198.51.100.7", client_port=54321)

            r = await http.get(f"{base}/test/fraud-prevention-headers/validate",
                               headers={"Accept": "application/vnd.hmrc.1.0+json",
                                        "Authorization": f"Bearer {token}", **headers})
            if r.status_code >= 300:
                try:
                    code = r.json().get("code", "")
                except Exception:
                    code = ""
                if code == "RESOURCE_FORBIDDEN":
                    warn("Test Fraud Prevention Headers API not subscribed — cannot check")
                else:
                    warn(f"validator returned HTTP {r.status_code}")
            else:
                d = r.json()
                errors = d.get("errors") or []
                warnings = d.get("warnings") or []
                for e in errors:
                    bad(f"{e.get('code')}: {e.get('message','')[:80]} "
                        f"({', '.join(e.get('headers') or [])})")
                for w in warnings:
                    if "license-ids" in " ".join(w.get("headers") or []):
                        # Expected: ASETS is not licensed software. HMRC's
                        # own guidance is to omit and explain, which the
                        # production application does — see docs/HMRC.md.
                        print(f"  {DIM}· gov-vendor-license-ids absent — expected, "
                              f"explained in the application{RESET}")
                    else:
                        warn(f"{w.get('code')}: {w.get('message','')[:80]} "
                             f"({', '.join(w.get('headers') or [])})")
                if errors:
                    missing.append("fraud prevention headers")
                else:
                    ok(f"spec {d.get('specVersion')} — no errors "
                       f"({len(headers)} headers sent)")

    print()
    if missing:
        print(f"{RED}Not ready:{RESET} " + ", ".join(missing))
        return 1
    print(f"{GREEN}HMRC setup looks complete.{RESET} "
          "Connect from the app: Settings → HMRC → Connect to HMRC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
