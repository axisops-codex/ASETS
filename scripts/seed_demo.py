#!/usr/bin/env python3
"""Seed a demo/reviewer account with believable data.

Both stores need a working login to review the app, and an empty account shows
none of the features. Run this once against the production API after deploying.

    python3 scripts/seed_demo.py https://asets-api-xxxxx.run.app demo@example.com 'a-password'

Re-running is safe: if the account exists it logs in and tops the data up only
when the account is empty.
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta


def call(base, path, method="GET", body=None, token=None):
    req = urllib.request.Request(f"{base}/api{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return e.code, {"detail": raw.decode(errors="replace")}


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    base, email, password = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]

    status, body = call(base, "/auth/register", "POST", {"email": email, "password": password, "name": "Dr Sam Reviewer"})
    if status == 409:
        status, body = call(base, "/auth/login", "POST", {"email": email, "password": password})
    if status >= 400:
        print(f"! auth failed ({status}): {body.get('detail')}")
        return 1
    token = body["access_token"]
    print(f"✓ signed in as {email}")

    call(base, "/auth/profile", "PUT", {
        "name": "Dr Sam Reviewer",
        "business_name": "Sam Reviewer Psychology",
        "address": "12 Harley Mews",
        "city": "London",
        "postcode": "W1G 6AB",
        "utr": "1234567890",
        "bank": {
            "bank_name": "Barclays", "account_name": "S Reviewer",
            "sort_code": "20-00-00", "account_number": "12345678",
            "reference": "Please use the invoice number",
        },
        "services": [
            {"id": "svc-1", "name": "Individual therapy session (50 min)", "price": 95, "unit": "session"},
            {"id": "svc-2", "name": "ADHD assessment", "price": 850, "unit": "fixed"},
        ],
    }, token)
    print("✓ business profile set")

    _, existing = call(base, "/invoices", token=token)
    if isinstance(existing, list) and existing:
        print(f"✓ account already has {len(existing)} invoices — nothing more to seed")
        return 0

    clients = []
    for c in [
        {"name": "Northgate Wellbeing Ltd", "contact_name": "Priya Shah", "email": "accounts@example.com",
         "address": "4 Northgate Street, Manchester, M1 2AB", "rate": 95},
        {"name": "Harbour Occupational Health", "contact_name": "Tom Ellis", "email": "finance@example.com",
         "address": "1 Dockside Way, Bristol, BS1 4RN", "rate": 110},
    ]:
        _, doc = call(base, "/clients", "POST", c, token)
        clients.append(doc["id"])
    print(f"✓ {len(clients)} clients")

    today = date.today()
    invoices = [
        (clients[0], today - timedelta(days=54), "paid", [("Individual therapy session (50 min)", 8, 95)]),
        (clients[1], today - timedelta(days=26), "paid", [("Teleconsultation (video)", 6, 110)]),
        (clients[0], today - timedelta(days=12), "sent", [("Individual therapy session (50 min)", 4, 95),
                                                          ("Report writing", 1, 180)]),
        (clients[1], today - timedelta(days=3), "sent", [("ADHD assessment", 1, 850)]),
    ]
    for client_id, issued, status_, items in invoices:
        call(base, "/invoices", "POST", {
            "client_id": client_id,
            "issue_date": issued.isoformat(),
            "due_date": (issued + timedelta(days=30)).isoformat(),
            "status": status_,
            "items": [{"description": d, "quantity": q, "unit_price": p} for d, q, p in items],
            "notes": "Thank you — payment within 30 days.",
        }, token)
    print(f"✓ {len(invoices)} invoices")

    expenses = [
        ("Supervision", "Monthly clinical supervision", 120.0, 40),
        ("Software", "Video consultation platform", 24.0, 33),
        ("Insurance", "Professional indemnity — annual", 410.0, 61),
        ("Training / CPD", "EMDR refresher workshop", 275.0, 20),
        ("Professional fees", "HCPC registration", 98.12, 9),
        ("Phone / Internet", "Mobile plan (business share)", 18.5, 4),
    ]
    for category, desc, amount, days_ago in expenses:
        call(base, "/expenses", "POST", {
            "category": category, "description": desc, "amount": amount,
            "date": (today - timedelta(days=days_ago)).isoformat(),
        }, token)
    print(f"✓ {len(expenses)} expenses")
    print("\nDemo account ready. Put these credentials in the store review notes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
