from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, date
import jwt
import bcrypt
import re
import ipaddress
import httpx
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "PsyBooks")

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
TOKEN_DAYS = 30

app = FastAPI()
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("psybooks")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc).timestamp() + TOKEN_DAYS * 86400,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(cred: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = cred.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = await db.users.find_one({"id": user_id, "deleted_at": None}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name", ""),
        "business_name": u.get("business_name", ""),
        "address": u.get("address", ""),
        "utr": u.get("utr", ""),
        "settings": u.get("settings", {}),
    }


# ---------------------------------------------------------------------------
# Email (Emergent managed Resend) — send invoice to client
# ---------------------------------------------------------------------------
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str, reply_to: Optional[str] = None) -> Optional[str]:
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    if reply_to:
        payload["contact_email"] = reply_to
    try:
        async with httpx.AsyncClient(timeout=30) as hc:
            resp = await hc.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=502, detail="Could not send the email")
    except Exception as e:
        logger.error(f"Email send error: {e}")
        raise HTTPException(status_code=500, detail="Could not send the email")


def _money(n: float) -> str:
    return f"£{(n or 0):,.2f}"


def build_invoice_email_html(inv: dict, biz: dict, client: dict) -> str:
    biz_name = escape(biz.get("business_name") or biz.get("name") or "PsyBooks")
    rows = ""
    for it in inv.get("items", []):
        amt = (it.get("quantity", 0) or 0) * (it.get("unit_price", 0) or 0)
        rows += (
            f'<tr><td style="padding:8px 4px;border-bottom:1px solid #eee;font-size:14px">{escape(str(it.get("description","")))}</td>'
            f'<td style="padding:8px 4px;border-bottom:1px solid #eee;font-size:14px;text-align:right">{it.get("quantity",0)}</td>'
            f'<td style="padding:8px 4px;border-bottom:1px solid #eee;font-size:14px;text-align:right">{_money(it.get("unit_price",0))}</td>'
            f'<td style="padding:8px 4px;border-bottom:1px solid #eee;font-size:14px;text-align:right">{_money(amt)}</td></tr>'
        )
    notes = ""
    if inv.get("notes"):
        notes = (f'<p style="margin-top:20px;padding:14px;background:#F0F0EE;border-radius:10px;'
                 f'font-size:13px;color:#4A4D4A">{escape(inv["notes"])}</p>')
    return (
        f'<table role="presentation" width="100%" style="max-width:560px;margin:0 auto;'
        f'font-family:Arial,Helvetica,sans-serif;color:#1A1C1A"><tr><td style="padding:24px">'
        f'<p style="font-size:20px;font-weight:bold;color:#5F7161;margin:0">{biz_name}</p>'
        f'<h1 style="font-size:26px;margin:6px 0 2px">Invoice {escape(inv.get("number",""))}</h1>'
        f'<p style="color:#888;font-size:13px;margin:0">Issued {escape(inv.get("issue_date",""))}'
        + (f' · Due {escape(inv["due_date"])}' if inv.get("due_date") else "")
        + f'</p>'
        f'<p style="font-size:14px;margin:16px 0 4px"><strong>Billed to:</strong> {escape(client.get("name",""))}</p>'
        f'<table role="presentation" width="100%" style="border-collapse:collapse;margin-top:12px">'
        f'<tr><th style="text-align:left;font-size:11px;color:#9a9e9a;padding:8px 4px;border-bottom:2px solid #E5E5E3">DESCRIPTION</th>'
        f'<th style="text-align:right;font-size:11px;color:#9a9e9a;padding:8px 4px;border-bottom:2px solid #E5E5E3">QTY</th>'
        f'<th style="text-align:right;font-size:11px;color:#9a9e9a;padding:8px 4px;border-bottom:2px solid #E5E5E3">RATE</th>'
        f'<th style="text-align:right;font-size:11px;color:#9a9e9a;padding:8px 4px;border-bottom:2px solid #E5E5E3">AMOUNT</th></tr>'
        f'{rows}</table>'
        f'<p style="text-align:right;font-size:22px;font-weight:bold;margin:18px 0 0">Total: {_money(inv.get("total",0))}</p>'
        f'<p style="text-align:right;font-size:12px;color:#888;margin:2px 0">No VAT — exempt healthcare services.</p>'
        f'{notes}'
        f'<p style="font-size:12px;color:#888;margin-top:28px">Sent via PsyBooks on behalf of {biz_name}. '
        f'Reply to this email to reach them. We never ask for your password or card details by email.</p>'
        f'</td></tr></table>'
    )




# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    address: Optional[str] = None
    utr: Optional[str] = None
    settings: Optional[dict] = None


class ClientIn(BaseModel):
    name: str
    contact_name: str = ""
    email: str = ""
    address: str = ""
    notes: str = ""
    rate: Optional[float] = None


class InvoiceItem(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float = 0


class InvoiceIn(BaseModel):
    client_id: str
    issue_date: str  # ISO date (YYYY-MM-DD)
    due_date: Optional[str] = None
    items: List[InvoiceItem]
    notes: str = ""
    status: Literal["draft", "sent", "paid"] = "sent"


class InvoiceUpdate(BaseModel):
    status: Optional[Literal["draft", "sent", "paid"]] = None
    client_id: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    items: Optional[List[InvoiceItem]] = None
    notes: Optional[str] = None
    paid_date: Optional[str] = None


class ExpenseIn(BaseModel):
    category: str
    description: str = ""
    amount: float
    date: str  # ISO date


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.strip().lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = {
        "id": new_id(),
        "email": email,
        "password_hash": hash_password(body.password),
        "name": body.name.strip(),
        "business_name": "",
        "address": "",
        "utr": "",
        "settings": {"theme": "system", "cards": ["take_home", "hmrc", "cashflow", "recent"]},
        "created_at": now_iso(),
        "deleted_at": None,
    }
    await db.users.insert_one(user)
    return {"access_token": create_token(user["id"]), "user": public_user(user)}


@api_router.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email, "deleted_at": None})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"access_token": create_token(user["id"]), "user": public_user(user)}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api_router.put("/auth/profile")
async def update_profile(body: ProfileUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return public_user(fresh)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
@api_router.get("/clients")
async def list_clients(user: dict = Depends(get_current_user)):
    docs = await db.clients.find({"user_id": user["id"], "deleted_at": None}, {"_id": 0}).sort("name", 1).to_list(500)
    return docs


@api_router.post("/clients")
async def create_client(body: ClientIn, user: dict = Depends(get_current_user)):
    doc = {"id": new_id(), "user_id": user["id"], **body.dict(), "created_at": now_iso(), "deleted_at": None}
    await db.clients.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.put("/clients/{client_id}")
async def update_client(client_id: str, body: ClientIn, user: dict = Depends(get_current_user)):
    res = await db.clients.update_one({"id": client_id, "user_id": user["id"]}, {"$set": body.dict()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    doc = await db.clients.find_one({"id": client_id}, {"_id": 0})
    return doc


@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(get_current_user)):
    await db.clients.update_one({"id": client_id, "user_id": user["id"]}, {"$set": {"deleted_at": now_iso()}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
def invoice_total(items: List[dict]) -> float:
    return round(sum((it.get("quantity", 0) or 0) * (it.get("unit_price", 0) or 0) for it in items), 2)


async def enrich_invoice(inv: dict, user_id: str) -> dict:
    client = await db.clients.find_one({"id": inv.get("client_id"), "user_id": user_id}, {"_id": 0, "name": 1})
    inv["client_name"] = client["name"] if client else "Unknown client"
    return inv


@api_router.get("/invoices")
async def list_invoices(user: dict = Depends(get_current_user)):
    docs = await db.invoices.find({"user_id": user["id"], "deleted_at": None}, {"_id": 0}).sort("issue_date", -1).to_list(1000)
    for d in docs:
        await enrich_invoice(d, user["id"])
    return docs


@api_router.post("/invoices")
async def create_invoice(body: InvoiceIn, user: dict = Depends(get_current_user)):
    count = await db.invoices.count_documents({"user_id": user["id"]})
    items = [it.dict() for it in body.items]
    doc = {
        "id": new_id(),
        "user_id": user["id"],
        "number": f"INV-{count + 1:04d}",
        "client_id": body.client_id,
        "issue_date": body.issue_date,
        "due_date": body.due_date,
        "items": items,
        "notes": body.notes,
        "status": body.status,
        "total": invoice_total(items),
        "paid_date": today_iso_date() if body.status == "paid" else None,
        "created_at": now_iso(),
        "deleted_at": None,
    }
    await db.invoices.insert_one(doc)
    doc.pop("_id", None)
    await enrich_invoice(doc, user["id"])
    return doc


@api_router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, body: InvoiceUpdate, user: dict = Depends(get_current_user)):
    inv = await db.invoices.find_one({"id": invoice_id, "user_id": user["id"]})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if "items" in updates:
        updates["items"] = [it if isinstance(it, dict) else it.dict() for it in updates["items"]]
        updates["total"] = invoice_total(updates["items"])
    if "status" in updates:
        if updates["status"] == "paid":
            updates["paid_date"] = body.paid_date or inv.get("paid_date") or today_iso_date()
        else:
            updates["paid_date"] = None
    if updates:
        await db.invoices.update_one({"id": invoice_id}, {"$set": updates})
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    await enrich_invoice(doc, user["id"])
    return doc


@api_router.post("/invoices/{invoice_id}/email")
async def email_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    inv = await db.invoices.find_one({"id": invoice_id, "user_id": user["id"], "deleted_at": None}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    client = await db.clients.find_one({"id": inv.get("client_id"), "user_id": user["id"]}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    to = (client.get("email") or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Add an email to this client first")
    biz_name = user.get("business_name") or user.get("name") or "your therapist"
    subject = f"Invoice {inv.get('number','')} from {biz_name}"
    html = build_invoice_email_html(inv, user, client)
    email_id = await send_email(to=to, subject=subject, html=html, reply_to=user.get("email"))
    return {"ok": True, "email_id": email_id, "sent_to": to}


@api_router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    await db.invoices.update_one({"id": invoice_id, "user_id": user["id"]}, {"$set": {"deleted_at": now_iso()}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
@api_router.get("/expenses")
async def list_expenses(user: dict = Depends(get_current_user)):
    docs = await db.expenses.find({"user_id": user["id"], "deleted_at": None}, {"_id": 0}).sort("date", -1).to_list(1000)
    return docs


@api_router.post("/expenses")
async def create_expense(body: ExpenseIn, user: dict = Depends(get_current_user)):
    doc = {"id": new_id(), "user_id": user["id"], **body.dict(), "created_at": now_iso(), "deleted_at": None}
    await db.expenses.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.put("/expenses/{expense_id}")
async def update_expense(expense_id: str, body: ExpenseIn, user: dict = Depends(get_current_user)):
    res = await db.expenses.update_one({"id": expense_id, "user_id": user["id"]}, {"$set": body.dict()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    doc = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    return doc


@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, user: dict = Depends(get_current_user)):
    await db.expenses.update_one({"id": expense_id, "user_id": user["id"]}, {"$set": {"deleted_at": now_iso()}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# HMRC tax calculation (England & NI, 2024/25 rates)
# ---------------------------------------------------------------------------
PERSONAL_ALLOWANCE = 12570.0
BASIC_LIMIT = 50270.0
HIGHER_LIMIT = 125140.0
BASIC_RATE = 0.20
HIGHER_RATE = 0.40
ADDITIONAL_RATE = 0.45
# National Insurance Class 4 (2024/25): 6% between LPL and UPL, 2% above
NI_LOWER = 12570.0
NI_UPPER = 50270.0
NI_MAIN_RATE = 0.06
NI_UPPER_RATE = 0.02


def compute_tax(sales: float, expenses: float) -> dict:
    profit = round(sales - expenses, 2)
    taxable_profit = max(0.0, profit)

    # Personal allowance taper above £100k
    pa = PERSONAL_ALLOWANCE
    if taxable_profit > 100000:
        pa = max(0.0, PERSONAL_ALLOWANCE - (taxable_profit - 100000) / 2)

    taxable = max(0.0, taxable_profit - pa)
    basic_band = max(0.0, BASIC_LIMIT - PERSONAL_ALLOWANCE)  # 37700
    higher_band = max(0.0, HIGHER_LIMIT - BASIC_LIMIT)       # 74870

    bands = []
    income_tax = 0.0
    if taxable > 0:
        b = min(taxable, basic_band)
        if b > 0:
            t = b * BASIC_RATE
            income_tax += t
            bands.append({"label": "Basic rate (20%)", "amount": round(b, 2), "tax": round(t, 2)})
        rem = taxable - b
        if rem > 0:
            h = min(rem, higher_band)
            t = h * HIGHER_RATE
            income_tax += t
            bands.append({"label": "Higher rate (40%)", "amount": round(h, 2), "tax": round(t, 2)})
            rem2 = rem - h
            if rem2 > 0:
                t = rem2 * ADDITIONAL_RATE
                income_tax += t
                bands.append({"label": "Additional rate (45%)", "amount": round(rem2, 2), "tax": round(t, 2)})

    # National Insurance Class 4
    ni = 0.0
    if taxable_profit > NI_LOWER:
        ni += (min(taxable_profit, NI_UPPER) - NI_LOWER) * NI_MAIN_RATE
    if taxable_profit > NI_UPPER:
        ni += (taxable_profit - NI_UPPER) * NI_UPPER_RATE

    income_tax = round(income_tax, 2)
    ni = round(ni, 2)
    total_due = round(income_tax + ni, 2)
    take_home = round(profit - total_due, 2)

    return {
        "sales": round(sales, 2),
        "expenses": round(expenses, 2),
        "profit": profit,
        "personal_allowance": round(pa, 2),
        "taxable_income": round(taxable, 2),
        "bands": bands,
        "income_tax": income_tax,
        "national_insurance": ni,
        "total_due": total_due,
        "take_home": take_home,
    }


def in_range(d: Optional[str], start: str, end: str) -> bool:
    if not d:
        return False
    return start <= d[:10] <= end


@api_router.get("/summary")
async def summary(start: str, end: str, user: dict = Depends(get_current_user)):
    invoices = await db.invoices.find({"user_id": user["id"], "deleted_at": None}, {"_id": 0}).to_list(2000)
    expenses = await db.expenses.find({"user_id": user["id"], "deleted_at": None}, {"_id": 0}).to_list(2000)

    inv_in = [i for i in invoices if in_range(i.get("issue_date"), start, end)]
    exp_in = [e for e in expenses if in_range(e.get("date"), start, end)]

    sales = round(sum(i.get("total", 0) for i in inv_in), 2)
    paid = round(sum(i.get("total", 0) for i in inv_in if i.get("status") == "paid"), 2)
    outstanding = round(sum(i.get("total", 0) for i in inv_in if i.get("status") in ("sent", "draft")), 2)
    total_expenses = round(sum(e.get("amount", 0) for e in exp_in), 2)

    tax = compute_tax(sales, total_expenses)

    # expenses breakdown by category
    by_cat: dict = {}
    for e in exp_in:
        c = e.get("category", "Other")
        by_cat[c] = round(by_cat.get(c, 0) + e.get("amount", 0), 2)

    # monthly cashflow (income vs expenses) within range
    months: dict = {}
    for i in inv_in:
        m = (i.get("issue_date") or "")[:7]
        if m:
            months.setdefault(m, {"income": 0, "expenses": 0})
            months[m]["income"] = round(months[m]["income"] + i.get("total", 0), 2)
    for e in exp_in:
        m = (e.get("date") or "")[:7]
        if m:
            months.setdefault(m, {"income": 0, "expenses": 0})
            months[m]["expenses"] = round(months[m]["expenses"] + e.get("amount", 0), 2)
    cashflow = [{"month": k, **v} for k, v in sorted(months.items())]

    return {
        "start": start,
        "end": end,
        "sales": sales,
        "paid": paid,
        "outstanding": outstanding,
        "expenses": total_expenses,
        "invoice_count": len(inv_in),
        "expense_count": len(exp_in),
        "tax": tax,
        "expenses_by_category": [{"category": k, "amount": v} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
        "cashflow": cashflow,
    }


@api_router.get("/export/csv")
async def export_csv(start: str, end: str, user: dict = Depends(get_current_user)):
    invoices = await db.invoices.find({"user_id": user["id"], "deleted_at": None}, {"_id": 0}).to_list(2000)
    expenses = await db.expenses.find({"user_id": user["id"], "deleted_at": None}, {"_id": 0}).to_list(2000)
    clients = await db.clients.find({"user_id": user["id"]}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    cmap = {c["id"]: c.get("name", "") for c in clients}
    inv_in = sorted([i for i in invoices if in_range(i.get("issue_date"), start, end)], key=lambda x: x.get("issue_date", ""))
    exp_in = sorted([e for e in expenses if in_range(e.get("date"), start, end)], key=lambda x: x.get("date", ""))

    def esc(v) -> str:
        s = "" if v is None else str(v)
        if any(c in s for c in [",", '"', "\n"]):
            s = '"' + s.replace('"', '""') + '"'
        return s

    lines = [f"PsyBooks export,{start} to {end}", "", "INCOME (Invoices)",
             "Date,Invoice,Client,Description,Amount,Status,Paid date"]
    sales = 0.0
    for i in inv_in:
        desc = "; ".join(str(it.get("description", "")) for it in i.get("items", []))
        sales += i.get("total", 0) or 0
        lines.append(",".join(esc(x) for x in [i.get("issue_date"), i.get("number"), cmap.get(i.get("client_id"), ""),
                     desc, f"{i.get('total',0):.2f}", i.get("status"), i.get("paid_date") or ""]))
    lines += ["", "EXPENSES", "Date,Category,Description,Amount"]
    total_exp = 0.0
    for e in exp_in:
        total_exp += e.get("amount", 0) or 0
        lines.append(",".join(esc(x) for x in [e.get("date"), e.get("category"), e.get("description") or "", f"{e.get('amount',0):.2f}"]))

    tax = compute_tax(sales, total_exp)
    lines += ["", "SUMMARY",
              f"Total sales,{sales:.2f}",
              f"Total expenses,{total_exp:.2f}",
              f"Taxable profit,{tax['profit']:.2f}",
              f"Income tax (est),{tax['income_tax']:.2f}",
              f"National Insurance (est),{tax['national_insurance']:.2f}",
              f"Tax to set aside (est),{tax['total_due']:.2f}",
              f"Take home (est),{tax['take_home']:.2f}",
              "", "No VAT charged - exempt healthcare services. Estimates based on 2024/25 rates."]
    csv = "\n".join(lines)
    return {"csv": csv, "filename": f"psybooks_{start}_to_{end}.csv"}


@api_router.get("/")
async def root():
    return {"message": "PsyBooks API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
