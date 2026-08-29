"""Iteration 3 regression tests:
1. POST /api/expenses/scan -> AI receipt extraction + object storage
2. GET /api/files/{path}?token=... (owner 200 / 401 no token / 403 other user)
3. Expense with receipt_path persists via POST + GET /api/expenses
4. POST /api/invoices/{id}/email — auto-marks draft as sent, records emailed_at
5. GET /api/summary?group=day  — daily cashflow buckets and net = sales - expenses
"""
import os
import io
import base64
import uuid
import pytest
import requests
from PIL import Image, ImageDraw, ImageFont

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or "https://freelance-finance-35.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# --------------------------- helpers ---------------------------
def _register(name="Dr Iter3"):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"iter3_{uuid.uuid4().hex[:10]}@psybooks.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": name})
    assert r.status_code == 200, r.text
    data = r.json()
    token = data["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s, token, data["user"]


def _build_receipt_jpeg_b64() -> str:
    """Build a realistic receipt-looking JPEG with text so gemini-3-flash-preview extracts fields.
    Contains: merchant, date, description item, TOTAL. Real edges/text -> passes image_testing rules.
    """
    W, H = 480, 720
    img = Image.new("RGB", (W, H), (245, 245, 240))
    draw = ImageDraw.Draw(img)
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_mid = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except Exception:
        font_big = ImageFont.load_default()
        font_mid = font_big
        font_small = font_big

    y = 30
    draw.text((W // 2 - 90, y), "NOTION LABS", fill=(10, 10, 10), font=font_big); y += 44
    draw.text((W // 2 - 100, y), "1 Market Street, London", fill=(30, 30, 30), font=font_small); y += 26
    draw.text((W // 2 - 70, y), "VAT: GB123456789", fill=(30, 30, 30), font=font_small); y += 36
    draw.line((20, y, W - 20, y), fill=(60, 60, 60), width=2); y += 20
    draw.text((30, y), "Date: 2024-11-15", fill=(0, 0, 0), font=font_mid); y += 30
    draw.text((30, y), "Receipt #: 8834", fill=(0, 0, 0), font=font_mid); y += 40
    draw.text((30, y), "Notion Personal Pro", fill=(0, 0, 0), font=font_mid)
    draw.text((W - 110, y), "GBP 14.99", fill=(0, 0, 0), font=font_mid); y += 30
    draw.text((30, y), "Monthly subscription", fill=(80, 80, 80), font=font_small); y += 40
    draw.line((20, y, W - 20, y), fill=(60, 60, 60), width=2); y += 20
    draw.text((30, y), "Subtotal", fill=(0, 0, 0), font=font_mid)
    draw.text((W - 110, y), "GBP 14.99", fill=(0, 0, 0), font=font_mid); y += 30
    draw.text((30, y), "TOTAL", fill=(0, 0, 0), font=font_big)
    draw.text((W - 130, y), "GBP 14.99", fill=(0, 0, 0), font=font_big); y += 60
    draw.text((30, y), "Paid by Visa **** 4242", fill=(30, 30, 30), font=font_small); y += 24
    draw.text((30, y), "Thank you!", fill=(30, 30, 30), font=font_small)

    # Add a bit of edge/texture noise so the image isn't uniform
    for i in range(0, W, 20):
        draw.line((i, H - 30, i + 10, H - 30), fill=(0, 0, 0), width=1)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


VALID_CATEGORIES = {
    "Software", "Office", "Travel", "Meals", "Marketing",
    "Professional", "Training", "Equipment", "Rent", "Other",
    "CPD", "Supervision", "Insurance", "Fees", "Membership",
    "Utilities", "Phone", "Internet",
}


# --------------------------- fixtures ---------------------------
@pytest.fixture(scope="module")
def owner():
    s, token, user = _register(name="Owner A")
    return {"session": s, "token": token, "user": user}


@pytest.fixture(scope="module")
def other_user():
    s, token, user = _register(name="Other B")
    return {"session": s, "token": token, "user": user}


@pytest.fixture(scope="module")
def scanned(owner):
    """Scan a receipt once and reuse across tests."""
    b64 = _build_receipt_jpeg_b64()
    r = owner["session"].post(f"{API}/expenses/scan", json={"image_base64": b64}, timeout=90)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------- 1. Receipt scan ---------------------------
class TestExpenseScan:
    def test_scan_returns_expected_fields(self, scanned):
        for key in ("amount", "currency", "date", "merchant", "description", "category", "receipt_path"):
            assert key in scanned, f"missing key: {key} in {scanned}"
        # Amount should be numeric
        assert isinstance(scanned["amount"], (int, float))
        # Category must be one of the fixed list
        assert scanned["category"] in VALID_CATEGORIES, f"category={scanned['category']}"
        # receipt_path must be under psybooks/uploads/{user_id}/
        rp = scanned["receipt_path"]
        assert rp and rp.startswith("psybooks/uploads/"), rp

    def test_scan_amount_matches_total_on_receipt(self, scanned):
        # Vision model should return 14.99 for our synthetic receipt.
        # Allow ±0.5 to be robust to occasional OCR wobble but flag deviation.
        assert abs(float(scanned["amount"]) - 14.99) < 0.5, f"amount={scanned['amount']}"


# --------------------------- 2. /api/files auth ---------------------------
class TestFilesAccess:
    def test_owner_can_fetch_file_with_token_query(self, owner, scanned):
        url = f"{API}/files/{scanned['receipt_path']}"
        r = requests.get(url, params={"token": owner["token"]}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("image/")

    def test_files_401_without_token(self, scanned):
        url = f"{API}/files/{scanned['receipt_path']}"
        r = requests.get(url, timeout=30)
        assert r.status_code == 401, r.text

    def test_files_403_for_different_user(self, other_user, scanned):
        url = f"{API}/files/{scanned['receipt_path']}"
        r = requests.get(url, params={"token": other_user["token"]}, timeout=30)
        assert r.status_code == 403, r.text


# --------------------------- 3. Expense with receipt_path persists ---------------------------
class TestExpensePersistsReceiptPath:
    def test_create_expense_with_receipt_path_and_list(self, owner, scanned):
        payload = {
            "category": scanned["category"] if scanned["category"] in VALID_CATEGORIES else "Software",
            "description": "TEST_ScannedNotion",
            "amount": float(scanned["amount"]),
            "date": scanned.get("date") or "2024-11-15",
            "receipt_path": scanned["receipt_path"],
        }
        r = owner["session"].post(f"{API}/expenses", json=payload)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["receipt_path"] == scanned["receipt_path"]
        exp_id = created["id"]

        # GET list must include it with receipt_path preserved
        r = owner["session"].get(f"{API}/expenses")
        assert r.status_code == 200
        rows = r.json()
        got = next((x for x in rows if x["id"] == exp_id), None)
        assert got is not None, "created expense not found in list"
        assert got.get("receipt_path") == scanned["receipt_path"]
        assert got.get("description") == "TEST_ScannedNotion"


# --------------------------- 4. Email invoice — emailed_at + auto-sent ---------------------------
class TestEmailInvoiceConfirmation:
    def _client(self, owner, email="delivered@resend.dev"):
        r = owner["session"].post(f"{API}/clients", json={
            "name": "TEST_ResendClient", "email": email, "rate": 100.0
        })
        assert r.status_code == 200, r.text
        return r.json()

    def _make_inv(self, owner, client_id, status):
        r = owner["session"].post(f"{API}/invoices", json={
            "client_id": client_id, "issue_date": "2024-11-20", "status": status,
            "items": [{"description": "Session", "quantity": 1, "unit_price": 100}],
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_email_draft_auto_marks_sent_and_records_emailed_at(self, owner):
        c = self._client(owner)
        inv = self._make_inv(owner, c["id"], "draft")
        assert inv["status"] == "draft"
        assert inv.get("emailed_at") in (None, "")

        r = owner["session"].post(f"{API}/invoices/{inv['id']}/email")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["status"] == "sent"
        assert d.get("emailed_at")

        # Verify GET /invoices shows the updated status and emailed_at
        r = owner["session"].get(f"{API}/invoices")
        assert r.status_code == 200
        got = next(x for x in r.json() if x["id"] == inv["id"])
        assert got["status"] == "sent"
        assert got.get("emailed_at") == d["emailed_at"]

    def test_email_sent_invoice_records_emailed_at_but_keeps_status(self, owner):
        c = self._client(owner)
        inv = self._make_inv(owner, c["id"], "sent")
        r = owner["session"].post(f"{API}/invoices/{inv['id']}/email")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "sent"
        assert d.get("emailed_at")
        r = owner["session"].get(f"{API}/invoices")
        got = next(x for x in r.json() if x["id"] == inv["id"])
        assert got["status"] == "sent"
        assert got.get("emailed_at") == d["emailed_at"]

    def test_email_paid_invoice_keeps_paid_but_records_emailed_at(self, owner):
        c = self._client(owner)
        inv = self._make_inv(owner, c["id"], "paid")
        r = owner["session"].post(f"{API}/invoices/{inv['id']}/email")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "paid"
        assert d.get("emailed_at")


# --------------------------- 5. Summary by day ---------------------------
class TestSummaryGroupDay:
    def test_summary_group_day_returns_daily_buckets_and_net(self, owner):
        # Seed a client + one sent invoice + one expense on distinct days in Nov 2024
        r = owner["session"].post(f"{API}/clients", json={"name": "TEST_SumClient", "rate": 100.0})
        assert r.status_code == 200
        cid = r.json()["id"]
        # invoice on 2024-11-05 for 300
        owner["session"].post(f"{API}/invoices", json={
            "client_id": cid, "issue_date": "2024-11-05", "status": "sent",
            "items": [{"description": "S", "quantity": 3, "unit_price": 100}],
        })
        # expense on 2024-11-07 for 50
        owner["session"].post(f"{API}/expenses", json={
            "category": "Software", "description": "TEST_SumExp",
            "amount": 50.0, "date": "2024-11-07",
        })
        r = owner["session"].get(f"{API}/summary", params={
            "start": "2024-11-01", "end": "2024-11-30", "group": "day",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["group"] == "day"
        assert "net" in d and "cashflow" in d
        # Net = sales - expenses for the range
        assert round(d["sales"] - d["expenses"], 2) == round(d["net"], 2)

        # Bucket keys must be YYYY-MM-DD
        keys = [b["bucket"] for b in d["cashflow"]]
        assert all(len(k) == 10 and k[4] == "-" and k[7] == "-" for k in keys), keys
        # Our seeded days should be represented
        by_day = {b["bucket"]: b for b in d["cashflow"]}
        assert "2024-11-05" in by_day
        assert by_day["2024-11-05"]["income"] >= 300.0
        assert "2024-11-07" in by_day
        assert by_day["2024-11-07"]["expenses"] >= 50.0

    def test_summary_group_week_returns_weekly_buckets(self, owner):
        r = owner["session"].get(f"{API}/summary", params={
            "start": "2024-11-01", "end": "2024-11-30", "group": "week",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["group"] == "week"
        # Weeks should be Monday-anchored ISO dates
        for b in d["cashflow"]:
            assert len(b["bucket"]) == 10
