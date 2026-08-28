"""Full backend E2E tests for PsyBooks API."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://freelance-finance-35.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---------------- Health ----------------
class TestHealth:
    def test_root_api(self, api):
        r = api.get(f"{API}/")
        assert r.status_code == 200
        assert "PsyBooks" in r.json().get("message", "")


# ---------------- Auth ----------------
class TestAuth:
    def test_register_returns_token_and_user(self, api):
        email = f"reg_{int(time.time()*1000)}@psybooks.com"
        r = api.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Reg"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "access_token" in d and d["user"]["email"] == email

    def test_register_duplicate_email(self, api, test_user):
        r = api.post(f"{API}/auth/register", json={"email": test_user["email"], "password": "secret123"})
        assert r.status_code == 409

    def test_login_success(self, api, test_user):
        r = api.post(f"{API}/auth/login", json={"email": test_user["email"], "password": test_user["password"]})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_bad_password(self, api, test_user):
        r = api.post(f"{API}/auth/login", json={"email": test_user["email"], "password": "wrong"})
        assert r.status_code == 401

    def test_me_with_token(self, api, auth_headers, test_user):
        r = api.get(f"{API}/auth/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == test_user["email"]

    def test_me_without_token(self, api):
        r = api.get(f"{API}/auth/me")
        assert r.status_code in (401, 403)

    def test_profile_update(self, api, auth_headers):
        r = api.put(f"{API}/auth/profile", json={"business_name": "PsyClinic", "utr": "1234567890",
                                                 "settings": {"theme": "dark", "cards": ["take_home", "hmrc"]}},
                    headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["business_name"] == "PsyClinic"
        assert d["settings"]["theme"] == "dark"


# ---------------- Clients ----------------
class TestClients:
    def test_client_crud_flow(self, api, auth_headers):
        # Create
        r = api.post(f"{API}/clients", json={"name": "TEST_Acme Health", "contact_name": "Jane", "email": "j@acme.io", "rate": 100.0}, headers=auth_headers)
        assert r.status_code == 200, r.text
        c = r.json()
        cid = c["id"]
        assert c["name"] == "TEST_Acme Health"
        assert "_id" not in c

        # List includes it
        r = api.get(f"{API}/clients", headers=auth_headers)
        assert r.status_code == 200
        assert any(x["id"] == cid for x in r.json())

        # Update
        r = api.put(f"{API}/clients/{cid}", json={"name": "TEST_Acme Updated", "contact_name": "J", "email": "", "address": "", "notes": "", "rate": 120.0}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Acme Updated"

        # Delete (soft)
        r = api.delete(f"{API}/clients/{cid}", headers=auth_headers)
        assert r.status_code == 200
        r = api.get(f"{API}/clients", headers=auth_headers)
        assert not any(x["id"] == cid for x in r.json())


@pytest.fixture(scope="session")
def sample_client(api, auth_headers):
    r = api.post(f"{API}/clients", json={"name": "TEST_MainClient", "rate": 100.0}, headers=auth_headers)
    assert r.status_code == 200
    return r.json()


# ---------------- Invoices ----------------
class TestInvoices:
    def test_create_invoice_auto_number_and_total(self, api, auth_headers, sample_client):
        payload = {
            "client_id": sample_client["id"],
            "issue_date": "2024-06-10",
            "due_date": "2024-07-10",
            "items": [
                {"description": "Session", "quantity": 4, "unit_price": 100},
                {"description": "Report", "quantity": 1, "unit_price": 250},
            ],
            "status": "sent",
        }
        r = api.post(f"{API}/invoices", json=payload, headers=auth_headers)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["total"] == 650.0
        assert inv["number"].startswith("INV-")
        assert inv["client_name"] == "TEST_MainClient"
        assert len(inv["number"]) == 8  # INV-000N -> 4 digits

    def test_update_invoice_mark_paid(self, api, auth_headers, sample_client):
        r = api.post(f"{API}/invoices", json={"client_id": sample_client["id"], "issue_date": "2024-06-11",
                                              "items": [{"description": "S", "quantity": 1, "unit_price": 200}],
                                              "status": "sent"}, headers=auth_headers)
        inv = r.json()
        r = api.put(f"{API}/invoices/{inv['id']}", json={"status": "paid"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "paid"

    def test_list_invoices(self, api, auth_headers):
        r = api.get(f"{API}/invoices", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) >= 2

    def test_delete_invoice(self, api, auth_headers, sample_client):
        r = api.post(f"{API}/invoices", json={"client_id": sample_client["id"], "issue_date": "2024-06-12",
                                              "items": [{"description": "S", "quantity": 1, "unit_price": 50}]},
                     headers=auth_headers)
        iid = r.json()["id"]
        r = api.delete(f"{API}/invoices/{iid}", headers=auth_headers)
        assert r.status_code == 200
        r = api.get(f"{API}/invoices", headers=auth_headers)
        assert not any(x["id"] == iid for x in r.json())


# ---------------- Expenses ----------------
class TestExpenses:
    def test_expense_crud(self, api, auth_headers):
        r = api.post(f"{API}/expenses", json={"category": "Software", "description": "Notion", "amount": 15.0, "date": "2024-06-15"}, headers=auth_headers)
        assert r.status_code == 200, r.text
        e = r.json()
        eid = e["id"]
        assert e["amount"] == 15.0

        # Update
        r = api.put(f"{API}/expenses/{eid}", json={"category": "Software", "description": "Notion Pro", "amount": 20.0, "date": "2024-06-15"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["amount"] == 20.0

        # List
        r = api.get(f"{API}/expenses", headers=auth_headers)
        assert any(x["id"] == eid for x in r.json())

        # Delete
        r = api.delete(f"{API}/expenses/{eid}", headers=auth_headers)
        assert r.status_code == 200


# ---------------- Summary / Tax ----------------
class TestSummary:
    def test_summary_returns_expected_fields(self, api, auth_headers):
        r = api.get(f"{API}/summary", params={"start": "2024-04-06", "end": "2025-04-05"}, headers=auth_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["sales", "paid", "outstanding", "expenses", "tax", "cashflow", "expenses_by_category"]:
            assert k in d
        for k in ["bands", "income_tax", "national_insurance", "total_due", "take_home", "profit"]:
            assert k in d["tax"]

    def test_tax_math_known_profit(self, api, auth_headers, sample_client):
        """Register a fresh user, add specific sales and expenses, verify HMRC math."""
        # New isolated user to control numbers
        email = f"tax_{int(time.time()*1000)}@psybooks.com"
        rr = api.post(f"{API}/auth/register", json={"email": email, "password": "secret123"})
        tok = rr.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

        c = api.post(f"{API}/clients", json={"name": "TEST_TaxClient"}, headers=h).json()
        # sales = 50,000; expenses = 10,000; profit = 40,000
        api.post(f"{API}/invoices", json={"client_id": c["id"], "issue_date": "2024-06-01",
                                          "items": [{"description": "s", "quantity": 1, "unit_price": 50000}],
                                          "status": "paid"}, headers=h)
        api.post(f"{API}/expenses", json={"category": "Rent", "amount": 10000, "date": "2024-06-01"}, headers=h)

        r = api.get(f"{API}/summary", params={"start": "2024-04-06", "end": "2025-04-05"}, headers=h)
        d = r.json()
        tax = d["tax"]

        # profit=40000, PA=12570, taxable=27430, all in basic 20% = 5486
        assert tax["profit"] == 40000.0
        assert tax["personal_allowance"] == 12570.0
        assert tax["taxable_income"] == 27430.0
        assert tax["income_tax"] == 5486.0
        # NI Class 4: (40000-12570)*6% = 27430*0.06 = 1645.80
        assert abs(tax["national_insurance"] - 1645.80) < 0.05
        assert abs(tax["total_due"] - (5486.0 + 1645.80)) < 0.05
        assert abs(tax["take_home"] - (40000 - tax["total_due"])) < 0.05

    def test_summary_date_filtering(self, api, auth_headers):
        # Range outside data
        r = api.get(f"{API}/summary", params={"start": "2010-01-01", "end": "2010-12-31"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["sales"] == 0
