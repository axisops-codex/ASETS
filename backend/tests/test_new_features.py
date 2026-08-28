"""Regression tests for iteration_2 features:
1. POST /api/invoices/{id}/email
2. Invoice paid_date lifecycle on status transitions
3. PUT /api/invoices/{id} full edit (client/dates/items/notes/status) recomputes total
4. GET /api/export/csv?start=&end=
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or "https://freelance-finance-35.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ----------- Local fresh fixtures (isolate from other test data) -----------
@pytest.fixture(scope="module")
def user_auth():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"feat_{uuid.uuid4().hex[:10]}@psybooks.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Dr Feat"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def client_with_email(user_auth):
    r = user_auth.post(f"{API}/clients", json={
        "name": "TEST_ClientResend",
        "email": "delivered@resend.dev",
        "rate": 100.0,
    })
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def client_no_email(user_auth):
    r = user_auth.post(f"{API}/clients", json={"name": "TEST_NoEmailClient"})
    assert r.status_code == 200, r.text
    return r.json()


def _make_invoice(session, client_id, status="sent", issue_date="2024-06-20",
                  items=None, notes=""):
    if items is None:
        items = [{"description": "Session", "quantity": 2, "unit_price": 100}]
    r = session.post(f"{API}/invoices", json={
        "client_id": client_id, "issue_date": issue_date, "items": items,
        "status": status, "notes": notes,
    })
    assert r.status_code == 200, r.text
    return r.json()


# ----------- 1. Email invoice -----------
class TestEmailInvoice:
    def test_email_success_with_client_email(self, user_auth, client_with_email):
        inv = _make_invoice(user_auth, client_with_email["id"])
        r = user_auth.post(f"{API}/invoices/{inv['id']}/email")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("sent_to") == "delivered@resend.dev"
        assert "email_id" in d  # Resend returns an id; may be None on stub, but key must exist

    def test_email_400_when_client_has_no_email(self, user_auth, client_no_email):
        inv = _make_invoice(user_auth, client_no_email["id"])
        r = user_auth.post(f"{API}/invoices/{inv['id']}/email")
        assert r.status_code == 400, r.text
        assert "email" in r.json().get("detail", "").lower()

    def test_email_404_for_unknown_invoice(self, user_auth):
        r = user_auth.post(f"{API}/invoices/does-not-exist/email")
        assert r.status_code == 404


# ----------- 2. paid_date lifecycle -----------
class TestPaidDateLifecycle:
    def test_paid_date_null_on_create_sent(self, user_auth, client_with_email):
        inv = _make_invoice(user_auth, client_with_email["id"], status="sent")
        assert inv["status"] == "sent"
        assert inv.get("paid_date") in (None, "")

    def test_paid_date_set_on_create_paid(self, user_auth, client_with_email):
        inv = _make_invoice(user_auth, client_with_email["id"], status="paid")
        assert inv["status"] == "paid"
        assert inv.get("paid_date"), "paid_date should be set on create-with-paid"
        # Should be today's ISO date
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        assert inv["paid_date"] == today

    def test_mark_paid_sets_paid_date(self, user_auth, client_with_email):
        inv = _make_invoice(user_auth, client_with_email["id"], status="sent")
        r = user_auth.put(f"{API}/invoices/{inv['id']}", json={"status": "paid"})
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "paid"
        assert d.get("paid_date")

    def test_reverting_to_sent_clears_paid_date(self, user_auth, client_with_email):
        inv = _make_invoice(user_auth, client_with_email["id"], status="paid")
        assert inv.get("paid_date")
        r = user_auth.put(f"{API}/invoices/{inv['id']}", json={"status": "sent"})
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "sent"
        assert d.get("paid_date") in (None, "")

    def test_reverting_to_draft_clears_paid_date(self, user_auth, client_with_email):
        inv = _make_invoice(user_auth, client_with_email["id"], status="paid")
        r = user_auth.put(f"{API}/invoices/{inv['id']}", json={"status": "draft"})
        assert r.status_code == 200
        assert r.json().get("paid_date") in (None, "")


# ----------- 3. Full edit invoice -----------
class TestEditInvoice:
    def test_edit_all_fields_recomputes_total(self, user_auth, client_with_email, client_no_email):
        inv = _make_invoice(user_auth, client_with_email["id"], status="sent",
                            issue_date="2024-06-10",
                            items=[{"description": "Old", "quantity": 1, "unit_price": 100}])
        assert inv["total"] == 100.0

        new_items = [
            {"description": "Session A", "quantity": 3, "unit_price": 120},
            {"description": "Report", "quantity": 1, "unit_price": 250},
        ]
        r = user_auth.put(f"{API}/invoices/{inv['id']}", json={
            "client_id": client_no_email["id"],
            "issue_date": "2024-07-15",
            "due_date": "2024-08-15",
            "items": new_items,
            "notes": "Edited notes",
            "status": "draft",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["client_id"] == client_no_email["id"]
        assert d["issue_date"] == "2024-07-15"
        assert d["due_date"] == "2024-08-15"
        assert d["notes"] == "Edited notes"
        assert d["status"] == "draft"
        assert d["total"] == 3 * 120 + 1 * 250  # 610
        assert d["client_name"] == "TEST_NoEmailClient"

        # Persistence — refetch via list
        r = user_auth.get(f"{API}/invoices")
        got = next(x for x in r.json() if x["id"] == inv["id"])
        assert got["total"] == 610.0
        assert got["notes"] == "Edited notes"


# ----------- 4. Export CSV -----------
class TestExportCSV:
    def test_export_csv_structure_and_client_names(self, user_auth, client_with_email):
        # Seed one invoice + one expense in a controlled window
        _make_invoice(user_auth, client_with_email["id"], status="paid",
                      issue_date="2024-06-01",
                      items=[{"description": "CSV Session", "quantity": 2, "unit_price": 150}])
        user_auth.post(f"{API}/expenses", json={
            "category": "Software", "description": "CSV Notion",
            "amount": 42.0, "date": "2024-06-02"
        })
        r = user_auth.get(f"{API}/export/csv", params={"start": "2024-04-06", "end": "2025-04-05"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "csv" in d and "filename" in d
        assert d["filename"] == "psybooks_2024-04-06_to_2025-04-05.csv"
        csv = d["csv"]
        # Sections
        assert "INCOME (Invoices)" in csv
        assert "EXPENSES" in csv
        assert "SUMMARY" in csv
        # Client name NOT blank in income section
        assert "TEST_ClientResend" in csv
        # Expense line present
        assert "Software" in csv and "42.00" in csv
        # Summary keys
        for k in ["Total sales", "Total expenses", "Taxable profit", "Tax to set aside"]:
            assert k in csv

    def test_export_csv_empty_range(self, user_auth):
        r = user_auth.get(f"{API}/export/csv", params={"start": "2010-01-01", "end": "2010-12-31"})
        assert r.status_code == 200
        csv = r.json()["csv"]
        assert "SUMMARY" in csv
        assert "Total sales,0.00" in csv
