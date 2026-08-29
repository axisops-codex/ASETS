"""Iteration 5 backend tests:
1. PUT /api/auth/profile persists new fields (city/postcode/company_reg/vat/ni/bank/services)
2. Register default values: bank.reference and services=[]
3. Companies House endpoints return 503 (not 500) when key not configured
4. Clients accept + persist company_number
5. Regression: invoices/expenses/summary still work
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL is required"
API = f"{BASE_URL}/api"


def _register():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"iter5_{uuid.uuid4().hex[:10]}@psybooks.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Dr Iter5"})
    assert r.status_code == 200, r.text
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return s, data["access_token"], data["user"]


@pytest.fixture(scope="module")
def owner():
    s, token, user = _register()
    return {"session": s, "token": token, "user": user}


# ---------- 2. Register defaults ----------
class TestRegisterDefaults:
    def test_register_returns_bank_reference_and_empty_services(self, owner):
        u = owner["user"]
        assert "bank" in u
        assert u["bank"].get("reference") == "Please use the invoice number"
        assert u["bank"].get("bank_name") == ""
        assert u["bank"].get("account_name") == ""
        assert u["bank"].get("sort_code") == ""
        assert u["bank"].get("account_number") == ""
        assert u.get("services") == []
        # New profile fields exposed
        for k in ("city", "postcode", "company_reg", "vat_number", "ni_number"):
            assert k in u, f"missing field {k}"


# ---------- 1. PUT /api/auth/profile persists new fields ----------
class TestProfileUpdate:
    def test_update_profile_persists_new_fields(self, owner):
        payload = {
            "business_name": "TEST_PsyCo Ltd",
            "address": "1 Sample Way",
            "city": "London",
            "postcode": "SW1A 1AA",
            "company_reg": "12345678",
            "vat_number": "GB123456789",
            "ni_number": "AB123456C",
            "utr": "1234567890",
            "bank": {
                "bank_name": "Monzo",
                "account_name": "TEST PsyCo Ltd",
                "sort_code": "04-00-04",
                "account_number": "12345678",
                "reference": "Please use the invoice number",
            },
            "services": [
                {"name": "CBT session", "price": 120.0, "unit": "session"},
                {"name": "Consulting", "price": 150.0, "unit": "hour"},
            ],
        }
        r = owner["session"].put(f"{API}/auth/profile", json=payload)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["city"] == "London"
        assert me["postcode"] == "SW1A 1AA"
        assert me["company_reg"] == "12345678"
        assert me["vat_number"] == "GB123456789"
        assert me["ni_number"] == "AB123456C"
        assert me["bank"]["bank_name"] == "Monzo"
        assert me["bank"]["sort_code"] == "04-00-04"
        assert me["bank"]["account_number"] == "12345678"
        assert len(me["services"]) == 2
        assert me["services"][0]["name"] == "CBT session"

        # GET /api/auth/me returns same
        r = owner["session"].get(f"{API}/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert d["city"] == "London"
        assert d["company_reg"] == "12345678"
        assert d["bank"]["account_number"] == "12345678"
        assert len(d["services"]) == 2


# ---------- 3. Companies House 503 without key ----------
class TestCompaniesHouseNoKey:
    def test_search_returns_503_when_not_configured(self, owner):
        r = owner["session"].get(f"{API}/companies/search", params={"q": "Tesco"})
        assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
        j = r.json()
        assert "not configured" in (j.get("detail") or "").lower()

    def test_profile_returns_503_when_not_configured(self, owner):
        r = owner["session"].get(f"{API}/companies/00445790")
        assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
        j = r.json()
        assert "not configured" in (j.get("detail") or "").lower()

    def test_endpoints_require_auth(self):
        r = requests.get(f"{API}/companies/search", params={"q": "Tesco"})
        assert r.status_code in (401, 403)


# ---------- 4. Clients accept company_number ----------
class TestClientCompanyNumber:
    def test_create_and_update_client_with_company_number(self, owner):
        r = owner["session"].post(f"{API}/clients", json={
            "name": "TEST_Acme Ltd",
            "email": "billing@acme.example",
            "address": "1 Acme Rd, London",
            "company_number": "00445790",
            "rate": 100.0,
        })
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["company_number"] == "00445790"
        cid = c["id"]

        # Update
        r = owner["session"].put(f"{API}/clients/{cid}", json={
            "name": "TEST_Acme Ltd",
            "email": "billing@acme.example",
            "address": "1 Acme Rd, London",
            "company_number": "12345678",
            "rate": 120.0,
        })
        assert r.status_code == 200
        assert r.json()["company_number"] == "12345678"

        # Verify via list
        r = owner["session"].get(f"{API}/clients")
        assert r.status_code == 200
        got = next(x for x in r.json() if x["id"] == cid)
        assert got["company_number"] == "12345678"


# ---------- 5. Regression ----------
class TestRegression:
    def test_invoices_create_list(self, owner):
        # need a client
        r = owner["session"].post(f"{API}/clients", json={"name": "TEST_InvClient", "rate": 100.0})
        assert r.status_code == 200
        cid = r.json()["id"]
        r = owner["session"].post(f"{API}/invoices", json={
            "client_id": cid, "issue_date": "2024-12-01", "status": "sent",
            "items": [{"description": "CBT session", "quantity": 2, "unit_price": 120}],
        })
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 240.0
        r = owner["session"].get(f"{API}/invoices")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_expenses_create_list(self, owner):
        r = owner["session"].post(f"{API}/expenses", json={
            "category": "Software", "description": "TEST_Iter5Exp",
            "amount": 25.0, "date": "2024-12-02",
        })
        assert r.status_code == 200
        r = owner["session"].get(f"{API}/expenses")
        assert r.status_code == 200

    def test_summary_still_works(self, owner):
        r = owner["session"].get(f"{API}/summary", params={
            "start": "2024-12-01", "end": "2024-12-31", "group": "month",
        })
        assert r.status_code == 200
        d = r.json()
        assert round(d["sales"] - d["expenses"], 2) == round(d["net"], 2)
