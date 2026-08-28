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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

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
    if updates:
        await db.invoices.update_one({"id": invoice_id}, {"$set": updates})
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    await enrich_invoice(doc, user["id"])
    return doc


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
