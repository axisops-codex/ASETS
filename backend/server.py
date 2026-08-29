from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, date, timedelta
import jwt
import bcrypt
import re
import httpx
import asyncpg
import base64
import json
import mimetypes
import shutil
import uuid as uuidlib
import requests
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse
from html import escape
from urllib.parse import quote

import crypto
from db import pool, repo, hmrc_repo
from hmrc import client as hmrc_client
from hmrc import fraud, mapping as hmrc_mapping
from hmrc import service as hmrc_service

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "psybooks"
_storage_key = None

COMPANIES_HOUSE_API_KEY = os.environ.get("COMPANIES_HOUSE_API_KEY", "")
COMPANIES_HOUSE_BASE_URL = os.environ.get("COMPANIES_HOUSE_BASE_URL", "https://api.company-information.service.gov.uk").rstrip("/")

# --- Self-host / production configuration ----------------------------------
# The app was built on the Emergent platform, whose managed proxy provides
# object storage and the vision model. Outside that platform (App Store /
# Play Store builds talk to our own API) both are swapped for standard
# providers, selected by env var. Defaults keep the Emergent behaviour.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
RECEIPT_MODEL = os.environ.get("RECEIPT_MODEL", "claude-opus-5")

# postgres = images live in the database alongside everything else (the
#            default: no object store to provision, and account deletion
#            cascades for free)
# local     = a mounted disk
# emergent  = Emergent platform object storage
STORAGE_BACKEND = (os.environ.get("STORAGE_BACKEND")
                   or ("emergent" if EMERGENT_LLM_KEY else "postgres")).lower()
LOCAL_STORAGE_DIR = Path(os.environ.get("LOCAL_STORAGE_DIR", str(ROOT_DIR / "var" / "receipts")))

def _resolve_provider(requested: str, keys: dict) -> str:
    """A provider is only 'configured' if its credential is actually there.

    Naming a provider in the environment without its key would otherwise
    make the feature look available and then fail mid-request; this way
    it reports as disabled and the app says so up front.
    """
    name = (requested or "").lower()
    if name and keys.get(name):
        return name
    if name:
        return ""
    return next((provider for provider, key in keys.items() if key), "")


LLM_PROVIDER = _resolve_provider(
    os.environ.get("LLM_PROVIDER", ""),
    {"emergent": EMERGENT_LLM_KEY, "anthropic": ANTHROPIC_API_KEY})

# Comma-separated list of allowed browser origins ("*" for any). Native app
# builds send no Origin header, so a strict list here costs the app nothing.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

# PostgreSQL. The pool is opened on startup; DATABASE_URL is the only
# thing the app needs to know about where the database lives (a Cloud SQL
# socket path works here exactly like a host:port).
DATABASE_URL = os.environ.get("DATABASE_URL", "")

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
TOKEN_DAYS = 30

@asynccontextmanager
async def lifespan(_: FastAPI):
    await pool.connect(DATABASE_URL or None,
                       max_size=int(os.environ.get("DB_POOL_MAX", "10")))
    try:
        await run_in_threadpool(init_storage)
        logging.getLogger("psybooks").info("Object storage initialised")
    except Exception as e:
        logging.getLogger("psybooks").error(
            f"Storage init failed (will retry on first upload): {e}")
    if hmrc_client.enabled():
        # HMRC requires the server's own public IP on every submission.
        found = await fraud.resolve_vendor_public_ip()
        logging.getLogger("psybooks").info(
            f"HMRC vendor public IP: {found or 'unresolved — header will be omitted'}")
    yield
    await pool.close()


app = FastAPI(lifespan=lifespan)
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
    try:
        payload = jwt.decode(cred.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session")
    async with pool.tenant(user_id) as conn:
        user = await repo.get_user(conn, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return user


def public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name", ""),
        "business_name": u.get("business_name", ""),
        "address": u.get("address", ""),
        "city": u.get("city", ""),
        "postcode": u.get("postcode", ""),
        "utr": u.get("utr", ""),
        "company_reg": u.get("company_reg", ""),
        "vat_number": u.get("vat_number", ""),
        "ni_number": u.get("ni_number", ""),
        "bank": u.get("bank", {}),
        "services": u.get("services", []),
        "settings": u.get("settings", {}),
    }


# ---------------------------------------------------------------------------
# Object storage (Emergent managed) + receipt AI extraction
# ---------------------------------------------------------------------------
def init_storage():
    """Emergent object storage handshake. A no-op for the other backends."""
    global _storage_key
    if STORAGE_BACKEND == "postgres":
        return "postgres"
    if STORAGE_BACKEND != "emergent":
        LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return "local"
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _emergent_put_object(path: str, data: bytes, content_type: str) -> dict:
    global _storage_key
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    if resp.status_code == 503:
        _storage_key = None
        key = init_storage()
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data,
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def _emergent_get_object(path: str) -> tuple:
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def _local_file(path: str) -> Path:
    """Resolve an object path inside LOCAL_STORAGE_DIR, refusing traversal."""
    rel = Path(path)
    if rel.is_absolute() or any(part in ("..", "") for part in rel.parts):
        raise ValueError("Invalid object path")
    target = (LOCAL_STORAGE_DIR / rel).resolve()
    root = LOCAL_STORAGE_DIR.resolve()
    if root not in target.parents:
        raise ValueError("Invalid object path")
    return target


def _local_put_object(path: str, data: bytes, content_type: str) -> dict:
    target = _local_file(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": path, "size": len(data)}


def _local_get_object(path: str) -> tuple:
    target = _local_file(path)
    if not target.is_file():
        raise FileNotFoundError(path)
    ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return target.read_bytes(), ctype


def _local_delete_prefix(prefix: str) -> None:
    """Best-effort removal of every object under a prefix (account deletion)."""
    try:
        folder = _local_file(prefix)
    except ValueError:
        return
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


async def put_object(path: str, data: bytes, content_type: str, user_id: str) -> dict:
    """Store a receipt image. The tenant is explicit because the postgres
    backend writes a row that row-level security has to accept."""
    if STORAGE_BACKEND == "postgres":
        async with pool.tenant(user_id) as conn:
            return await repo.put_receipt(conn, path=path, user_id=user_id,
                                          data=data, content_type=content_type)
    if STORAGE_BACKEND == "emergent":
        return await run_in_threadpool(_emergent_put_object, path, data, content_type)
    return await run_in_threadpool(_local_put_object, path, data, content_type)


async def get_object(path: str, user_id: str) -> tuple:
    if STORAGE_BACKEND == "postgres":
        async with pool.tenant(user_id) as conn:
            found = await repo.get_receipt(conn, path)
        if found is None:
            raise FileNotFoundError(path)
        return found
    if STORAGE_BACKEND == "emergent":
        return await run_in_threadpool(_emergent_get_object, path)
    return await run_in_threadpool(_local_get_object, path)


# Categories live in the database (asets.expense_categories) so the app,
# the receipt reader and the HMRC submission cannot disagree about them.
# Cached per instance; the list only changes by migration.
_categories_cache: Optional[list] = None


async def categories() -> list:
    global _categories_cache
    if _categories_cache is None:
        async with pool.anonymous() as conn:
            _categories_cache = await repo.expense_categories(conn)
    return _categories_cache


def receipt_schema(codes: list) -> dict:
    return {
        "type": "object",
        "properties": {
            "amount": {"type": "number"},
            "currency": {"type": "string"},
            "date": {"type": "string"},
            "merchant": {"type": "string"},
            "description": {"type": "string"},
            "category": {"type": "string", "enum": codes},
        },
        "required": ["amount", "currency", "date", "merchant", "description", "category"],
        "additionalProperties": False,
    }




def ocr_enabled() -> bool:
    return LLM_PROVIDER in ("emergent", "anthropic")


async def _vision_emergent(system: str, prompt: str, image_b64: str) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"receipt-{uuidlib.uuid4()}",
                   system_message=system).with_model("gemini", "gemini-3-flash-preview")
    raw = await chat.send_message(
        UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)]))
    return raw if isinstance(raw, str) else str(raw)


async def _vision_anthropic(system: str, prompt: str, image_b64: str, schema: dict) -> str:
    import anthropic

    llm = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    resp = await llm.messages.create(
        model=RECEIPT_MODEL,
        max_tokens=2048,
        system=system,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
    )
    return next((b.text for b in resp.content if b.type == "text"), "")


async def _vision_extract(system: str, prompt: str, image_b64: str, schema: dict) -> str:
    if LLM_PROVIDER == "emergent":
        return await _vision_emergent(system, prompt, image_b64)
    if LLM_PROVIDER == "anthropic":
        return await _vision_anthropic(system, prompt, image_b64, schema)
    raise RuntimeError("No vision provider configured (set EMERGENT_LLM_KEY or ANTHROPIC_API_KEY)")


async def extract_receipt(image_b64: str, cats_list: Optional[list] = None) -> dict:
    cats_list = cats_list if cats_list is not None else await categories()
    codes = [c["code"] for c in cats_list]
    # Give the model the hint text too — "meals only on overnight trips"
    # is the difference between an allowable expense and a wrong return.
    cats = "; ".join(f'{c["code"]} ({c["hint"]})' if c.get("hint") else c["code"]
                     for c in cats_list)
    system = (
        "You read UK business expense receipts for a self-employed practitioner. "
        "UK till receipts never identify the buyer — there is no customer name, "
        "VAT number or National Insurance number on them, so do not look for one. "
        "Work only from what the receipt shows: the merchant, the date and the "
        "amount actually paid. "
        "Return ONLY a compact JSON object, no prose, no code fences."
    )
    prompt = (
        "Extract the expense from this receipt image. If a QR code is present, use any text it encodes. "
        "amount is the final total actually paid — the figure after any discount and "
        "including service charge — not the sub-total and not a single line. "
        "UK receipts write dates as DD/MM/YYYY: read them that way. "
        "Return JSON with keys exactly: amount (number), currency (e.g. GBP), "
        "date (YYYY-MM-DD), merchant (string), description (short, what was bought), "
        f"category (choose the single best fit from: {cats}). "
        "A restaurant or pub bill is 'Client entertainment' unless it is clearly the "
        "practitioner's own meal while away overnight, which is 'Overnight trips'. "
        "If a value is unknown use null for strings and 0 for amount. JSON only."
    )
    text = (await _vision_extract(system, prompt, image_b64, receipt_schema(codes))).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    data = {}
    if start != -1 and end != -1:
        try:
            data = json.loads(text[start:end + 1])
        except Exception:
            data = {}
    cat = data.get("category")
    if cat not in codes:
        cat = "Other"
    try:
        amount = float(data.get("amount") or 0)
    except Exception:
        amount = 0.0
    return {
        "amount": round(amount, 2),
        "currency": data.get("currency") or "GBP",
        "date": data.get("date") or today_iso_date(),
        "merchant": data.get("merchant") or "",
        "description": data.get("description") or (data.get("merchant") or ""),
        "category": cat,
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
    city: Optional[str] = None
    postcode: Optional[str] = None
    utr: Optional[str] = None
    company_reg: Optional[str] = None
    vat_number: Optional[str] = None
    ni_number: Optional[str] = None
    bank: Optional[dict] = None
    services: Optional[list] = None
    settings: Optional[dict] = None


class ClientIn(BaseModel):
    name: str
    contact_name: str = ""
    email: str = ""
    address: str = ""
    company_number: str = ""
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
    receipt_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.strip().lower()
    async with pool.anonymous() as conn:
        if await repo.find_by_email(conn, email):
            raise HTTPException(status_code=409, detail="Email already registered")
        user = await repo.create_user(conn, email=email,
                                      password_hash=hash_password(body.password),
                                      name=body.name.strip())
    return {"access_token": create_token(user["id"]), "user": public_user(user)}


@api_router.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.strip().lower()
    async with pool.anonymous() as conn:
        user = await repo.find_by_email(conn, email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    async with pool.tenant(user["id"]) as conn:
        full = await repo.get_user(conn, user["id"])
    return {"access_token": create_token(full["id"]), "user": public_user(full)}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api_router.put("/auth/profile")
async def update_profile(body: ProfileUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    async with pool.tenant(user["id"]) as conn:
        fresh = await repo.update_profile(conn, user["id"], updates)
    return public_user(fresh)


@api_router.delete("/auth/account")
async def delete_account(user: dict = Depends(get_current_user)):
    """Permanent account deletion. Required by both stores for apps with sign-up.

    Runs under pool.privileged() because the cascade reaches the HMRC
    audit trail, which the database otherwise refuses to delete from.
    """
    uid = user["id"]
    async with pool.privileged(uid) as conn:
        await repo.delete_account(conn, uid)
    # The postgres backend cascades with the user row; the disk backend
    # has to be swept by hand.
    if STORAGE_BACKEND == "local":
        try:
            await run_in_threadpool(_local_delete_prefix, f"{APP_NAME}/uploads/{uid}")
        except Exception as e:  # never block deletion on storage cleanup
            logger.error(f"Receipt cleanup failed for {uid}: {e}")
    logger.info(f"Account deleted: {uid}")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
@api_router.get("/clients")
async def list_clients(user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        return await repo.list_clients(conn)


@api_router.post("/clients")
async def create_client(body: ClientIn, user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        return await repo.create_client(conn, user["id"], body.dict())


@api_router.put("/clients/{client_id}")
async def update_client(client_id: str, body: ClientIn, user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        updated = await repo.update_client(conn, client_id, body.dict())
    if updated is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return updated


@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        await repo.soft_delete_client(conn, client_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Companies House lookup (auto-fill customer company details)
# ---------------------------------------------------------------------------
def _fmt_ch_address(a: Optional[dict]) -> str:
    if not a:
        return ""
    parts = [a.get("premises"), a.get("address_line_1"), a.get("address_line_2"),
             a.get("locality"), a.get("region"), a.get("postal_code"), a.get("country")]
    return ", ".join([p for p in parts if p])


@api_router.get("/companies/search")
async def companies_search(q: str, user: dict = Depends(get_current_user)):
    if not COMPANIES_HOUSE_API_KEY:
        raise HTTPException(status_code=503, detail="Company lookup not configured. Add a Companies House API key in settings.")
    if len(q.strip()) < 2:
        return {"items": []}
    try:
        async with httpx.AsyncClient(base_url=COMPANIES_HOUSE_BASE_URL, timeout=12) as hc:
            resp = await hc.get("/search/companies", params={"q": q, "items_per_page": 8, "start_index": 0}, auth=(COMPANIES_HOUSE_API_KEY, ""))
        if resp.status_code == 401:
            raise HTTPException(status_code=502, detail="Companies House key was rejected")
        if resp.status_code == 429:
            raise HTTPException(status_code=503, detail="Company lookup busy, try again shortly")
        resp.raise_for_status()
        data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CH search error: {e}")
        raise HTTPException(status_code=502, detail="Company lookup failed")
    items = [
        {
            "company_number": it.get("company_number"),
            "company_name": it.get("title"),
            "company_status": it.get("company_status"),
            "address": _fmt_ch_address(it.get("address")),
        }
        for it in data.get("items", [])
        if it.get("company_number")
    ]
    return {"items": items}


@api_router.get("/companies/{company_number}")
async def companies_profile(company_number: str, user: dict = Depends(get_current_user)):
    if not COMPANIES_HOUSE_API_KEY:
        raise HTTPException(status_code=503, detail="Company lookup not configured")
    if not company_number.isalnum() or len(company_number) > 12:
        raise HTTPException(status_code=400, detail="Invalid company number")
    try:
        async with httpx.AsyncClient(base_url=COMPANIES_HOUSE_BASE_URL, timeout=12) as hc:
            resp = await hc.get(f"/company/{company_number}", auth=(COMPANIES_HOUSE_API_KEY, ""))
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Company not found")
        resp.raise_for_status()
        data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CH profile error: {e}")
        raise HTTPException(status_code=502, detail="Company lookup failed")
    return {
        "company_number": data.get("company_number"),
        "company_name": data.get("company_name"),
        "company_status": data.get("company_status"),
        "address": _fmt_ch_address(data.get("registered_office_address")),
    }


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
@api_router.get("/invoices")
async def list_invoices(user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        return await repo.list_invoices(conn)


@api_router.post("/invoices")
async def create_invoice(body: InvoiceIn, user: dict = Depends(get_current_user)):
    payload = body.dict()
    payload["items"] = [it if isinstance(it, dict) else it.dict() for it in payload["items"]]
    async with pool.tenant(user["id"]) as conn:
        try:
            return await repo.create_invoice(conn, user["id"], payload)
        except asyncpg.ForeignKeyViolationError:
            raise HTTPException(status_code=404, detail="Client not found")


@api_router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, body: InvoiceUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if "items" in updates:
        updates["items"] = [it if isinstance(it, dict) else it.dict() for it in updates["items"]]
    async with pool.tenant(user["id"]) as conn:
        updated = await repo.update_invoice(conn, invoice_id, user["id"], updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return updated


@api_router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        await repo.soft_delete_invoice(conn, invoice_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
@api_router.get("/expense-categories")
async def list_expense_categories(user: dict = Depends(get_current_user)):
    """What the picker shows. Served from the database so the app, the
    receipt reader and the HMRC submission cannot drift apart."""
    return {"categories": await categories()}


@api_router.get("/expenses")
async def list_expenses(user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        return await repo.list_expenses(conn)


@api_router.post("/expenses")
async def create_expense(body: ExpenseIn, user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        try:
            return await repo.create_expense(conn, user["id"], body.dict())
        except asyncpg.ForeignKeyViolationError:
            raise HTTPException(status_code=400, detail=f"Unknown category: {body.category}")


@api_router.put("/expenses/{expense_id}")
async def update_expense(expense_id: str, body: ExpenseIn, user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        try:
            updated = await repo.update_expense(conn, expense_id, body.dict())
        except asyncpg.ForeignKeyViolationError:
            raise HTTPException(status_code=400, detail=f"Unknown category: {body.category}")
    if updated is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    return updated


@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        await repo.soft_delete_expense(conn, expense_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Receipt scan (AI) + image storage
# ---------------------------------------------------------------------------
class ScanIn(BaseModel):
    image_base64: str


def _verify_receipt_owner(path: str, user_id: str) -> bool:
    # path convention: psybooks/uploads/{user_id}/{uuid}.ext
    parts = path.split("/")
    return len(parts) >= 3 and parts[0] == APP_NAME and parts[2] == user_id


@api_router.post("/expenses/scan")
async def scan_receipt(body: ScanIn, user: dict = Depends(get_current_user)):
    if not ocr_enabled():
        raise HTTPException(status_code=503, detail="Receipt scanning isn't set up on this server yet. Add the expense manually.")
    b64 = body.image_base64
    if "," in b64[:64]:
        b64 = b64.split(",", 1)[1]
    try:
        raw_bytes = base64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image")

    # Store the receipt image so the user keeps the proof
    receipt_path = None
    try:
        path = f"{APP_NAME}/uploads/{user['id']}/{uuidlib.uuid4().hex}.jpg"
        await put_object(path, raw_bytes, "image/jpeg", user["id"])
        receipt_path = path
    except Exception as e:
        logger.error(f"Receipt upload failed: {e}")

    # Extract fields with the vision model
    try:
        extracted = await extract_receipt(b64)
    except Exception as e:
        logger.error(f"Receipt extraction failed: {e}")
        raise HTTPException(status_code=502, detail="Could not read the receipt. Try a clearer photo.")

    extracted["receipt_path"] = receipt_path
    return extracted


@api_router.get("/files/{path:path}")
async def get_file(path: str, token: Optional[str] = None, cred: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))):
    jwt_token = token or (cred.credentials if cred else None)
    if not jwt_token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = jwt.decode(jwt_token, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not _verify_receipt_owner(path, user_id):
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        content, ctype = await get_object(path, user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    from fastapi import Response
    return Response(content=content, media_type=ctype)




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
async def summary(start: str, end: str, group: str = "month", user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        invoices = await repo.list_invoices(conn)
        expenses = await repo.list_expenses(conn)

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

    # cashflow bucketed by group: day (YYYY-MM-DD), week (ISO week start), month (YYYY-MM)
    def bucket_key(d: str) -> str:
        d = (d or "")[:10]
        if len(d) < 10:
            return ""
        if group == "day":
            return d
        if group == "week":
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                monday = dt - timedelta(days=dt.weekday())
                return monday.strftime("%Y-%m-%d")
            except Exception:
                return d
        return d[:7]  # month

    buckets: dict = {}
    for i in inv_in:
        k = bucket_key(i.get("issue_date"))
        if k:
            buckets.setdefault(k, {"income": 0, "expenses": 0})
            buckets[k]["income"] = round(buckets[k]["income"] + i.get("total", 0), 2)
    for e in exp_in:
        k = bucket_key(e.get("date"))
        if k:
            buckets.setdefault(k, {"income": 0, "expenses": 0})
            buckets[k]["expenses"] = round(buckets[k]["expenses"] + e.get("amount", 0), 2)
    cashflow = [{"bucket": k, "month": k, **v} for k, v in sorted(buckets.items())]

    return {
        "start": start,
        "end": end,
        "group": group,
        "sales": sales,
        "paid": paid,
        "outstanding": outstanding,
        "expenses": total_expenses,
        "net": round(sales - total_expenses, 2),
        "invoice_count": len(inv_in),
        "expense_count": len(exp_in),
        "tax": tax,
        "expenses_by_category": [{"category": k, "amount": v} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
        "cashflow": cashflow,
    }


@api_router.get("/export/csv")
async def export_csv(start: str, end: str, user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        invoices = await repo.list_invoices(conn)
        expenses = await repo.list_expenses(conn)
        cmap = await repo.client_name_map(conn)
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


# ---------------------------------------------------------------------------
# HMRC — Making Tax Digital for Income Tax
#
# The app talks to HMRC through this API (connection method
# MOBILE_APP_VIA_SERVER), so every call carries fraud prevention headers
# assembled from what the phone reports plus what only the server knows.
# ---------------------------------------------------------------------------
# HMRC documents the format as AA999999A and validates it authoritatively
# at their end. Encoding the full "impossible prefix" rules here would
# reject HMRC's own sandbox test users, so this only catches typos.
NINO_RE = re.compile(r"^[A-Z]{2}[0-9]{6}[A-D]$")

APP_RETURN_URL = os.environ.get("HMRC_APP_RETURN_URL", "asets://hmrc")


class NinoIn(BaseModel):
    nino: str


class BusinessIn(BaseModel):
    business_id: str


class SubmitQuarterIn(BaseModel):
    tax_year: str
    quarter: int = Field(ge=1, le=4)
    confirm: bool = False


def require_hmrc() -> None:
    if not hmrc_client.enabled():
        raise HTTPException(status_code=503,
                            detail="HMRC filing isn't set up on this server yet.")
    if not crypto.available():
        raise HTTPException(status_code=503,
                            detail="HMRC filing is unavailable: encryption key not configured.")


def device_headers(request: Request, user: dict) -> dict:
    """Fraud prevention headers for this request."""
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "")
    device = fraud.decode_device_header(request.headers.get("x-asets-device"))
    return fraud.build_headers(
        device,
        user_id=user["id"],
        client_ip=client_ip,
        client_port=request.client.port if request.client else None,
    )


def _hmrc_failure(status_code: int, payload) -> HTTPException:
    """HMRC error bodies are {code, message}; surface the message, not a 500."""
    message = "HMRC rejected the request."
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error_description") or message
        if isinstance(payload.get("errors"), list) and payload["errors"]:
            first = payload["errors"][0]
            message = f"{message} ({first.get('code')}: {first.get('message')})"
    return HTTPException(status_code=502 if status_code >= 500 else 400, detail=message)


@api_router.get("/hmrc/status")
async def hmrc_status(request: Request, user: dict = Depends(get_current_user)):
    configured = hmrc_client.enabled() and crypto.available()
    if not configured:
        return {"configured": False, "connected": False}
    async with pool.tenant(user["id"]) as conn:
        connection = await hmrc_repo.get_connection(conn, user["id"])
    headers = device_headers(request, user)
    today = date.today()
    tax_year = hmrc_mapping.tax_year_for(today)
    return {
        "configured": True,
        "connected": connection is not None,
        "environment": hmrc_client.config().environment,
        "nino_set": bool(connection and connection.get("nino")),
        "business_id": connection.get("business_id") if connection else None,
        "connected_at": connection.get("connected_at") if connection else None,
        "last_error": connection.get("last_error") if connection else None,
        "tax_year": tax_year,
        "quarters": hmrc_mapping.quarters(tax_year),
        "current_quarter": hmrc_mapping.current_quarter(tax_year, today),
        # Visible before a submission fails, not after.
        "missing_fraud_headers": fraud.missing(headers),
    }


@api_router.post("/hmrc/connect")
async def hmrc_connect(user: dict = Depends(get_current_user)):
    require_hmrc()
    cfg = hmrc_client.config()
    async with pool.tenant(user["id"]) as conn:
        state = await hmrc_repo.create_oauth_state(conn, user["id"], cfg.redirect_uri)
    return {"authorization_url": hmrc_client.authorization_url(state), "state": state}


@app.get("/api/hmrc/callback", include_in_schema=False)
async def hmrc_callback(code: str = "", state: str = "", error: str = "",
                        error_description: str = ""):
    """HMRC redirects the browser here after the user grants access.

    Not behind the bearer token — the browser has no session. The state
    token is the credential, and it is single-use and short-lived.
    """
    if error:
        return RedirectResponse(f"{APP_RETURN_URL}?status=denied&reason={quote(error_description or error)}")
    if not code or not state:
        return RedirectResponse(f"{APP_RETURN_URL}?status=error&reason=missing_code")

    async with pool.anonymous() as conn:
        claim = await hmrc_repo.consume_oauth_state(conn, state)
    if claim is None:
        return RedirectResponse(f"{APP_RETURN_URL}?status=error&reason=expired_link")

    try:
        tokens = await hmrc_client.exchange_code(code)
    except hmrc_client.HMRCError as e:
        logger.error(f"HMRC token exchange failed: {e.message}")
        return RedirectResponse(f"{APP_RETURN_URL}?status=error&reason={quote(e.message)}")

    async with pool.tenant(claim["user_id"]) as conn:
        await hmrc_repo.save_tokens(conn, claim["user_id"], tokens,
                                    hmrc_client.config().environment)
    logger.info("HMRC connected for %s", claim["user_id"])
    return RedirectResponse(f"{APP_RETURN_URL}?status=connected")


@api_router.post("/hmrc/disconnect")
async def hmrc_disconnect(user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        await hmrc_repo.disconnect(conn, user["id"])
    return {"connected": False}


@api_router.post("/hmrc/nino")
async def hmrc_set_nino(body: NinoIn, user: dict = Depends(get_current_user)):
    require_hmrc()
    nino = body.nino.replace(" ", "").upper()
    if not NINO_RE.match(nino):
        raise HTTPException(status_code=400,
                            detail="That doesn't look like a National Insurance number (e.g. QQ123456C).")
    async with pool.tenant(user["id"]) as conn:
        if await hmrc_repo.get_connection(conn, user["id"]) is None:
            raise HTTPException(status_code=409, detail="Connect to HMRC first.")
        await hmrc_repo.set_business(conn, user["id"], nino=nino)
    return {"nino_set": True}


@api_router.get("/hmrc/businesses")
async def hmrc_businesses(request: Request, user: dict = Depends(get_current_user)):
    require_hmrc()
    connection = await hmrc_service.require_connection(user["id"])
    try:
        status_code, payload = await hmrc_service.list_businesses(
            user_id=user["id"], connection=connection,
            fraud_headers=device_headers(request, user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if status_code >= 300:
        raise _hmrc_failure(status_code, payload)
    businesses = (payload or {}).get("listOfBusinesses", [])
    return {"businesses": [b for b in businesses if b.get("typeOfBusiness") == "self-employment"],
            "all": businesses}


@api_router.post("/hmrc/business")
async def hmrc_set_business(body: BusinessIn, user: dict = Depends(get_current_user)):
    require_hmrc()
    async with pool.tenant(user["id"]) as conn:
        if await hmrc_repo.get_connection(conn, user["id"]) is None:
            raise HTTPException(status_code=409, detail="Connect to HMRC first.")
        await hmrc_repo.set_business(conn, user["id"], business_id=body.business_id,
                                     business_type="self-employment")
    return {"business_id": body.business_id}


@api_router.get("/hmrc/obligations")
async def hmrc_obligations(request: Request, tax_year: Optional[str] = None,
                           user: dict = Depends(get_current_user)):
    require_hmrc()
    year = tax_year or hmrc_mapping.tax_year_for(date.today())
    connection = await hmrc_service.require_connection(user["id"])
    try:
        status_code, payload = await hmrc_service.obligations(
            user_id=user["id"], connection=connection,
            fraud_headers=device_headers(request, user), tax_year=year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if status_code >= 300:
        raise _hmrc_failure(status_code, payload)
    return {"tax_year": year, **(payload or {})}


@api_router.get("/hmrc/quarter-preview")
async def hmrc_quarter_preview(tax_year: Optional[str] = None, quarter: int = 0,
                               user: dict = Depends(get_current_user)):
    """What would be sent, before anything is sent.

    The user is making a declaration to HMRC; they get to see the exact
    figures first.
    """
    year = tax_year or hmrc_mapping.tax_year_for(date.today())
    periods = hmrc_mapping.quarters(year)
    if quarter:
        chosen = next((q for q in periods if q["quarter"] == quarter), None)
    else:
        chosen = hmrc_mapping.current_quarter(year, date.today()) or periods[-1]
    if chosen is None:
        raise HTTPException(status_code=400, detail="That quarter is not part of this tax year.")

    async with pool.tenant(user["id"]) as conn:
        invoices = await repo.list_invoices(conn)
        expenses = await repo.list_expenses(conn)
        category_records = await repo.expense_categories(conn)

    payload = hmrc_mapping.build_cumulative_payload(
        invoices=invoices, expenses=expenses, categories=category_records,
        period_start=date.fromisoformat(chosen["period_start"]),
        period_end=date.fromisoformat(chosen["period_end"]))
    return {"tax_year": year, "quarter": chosen,
            "payload": payload, "summary": hmrc_mapping.summarise_payload(payload)}


@api_router.post("/hmrc/submit-quarter")
async def hmrc_submit_quarter(body: SubmitQuarterIn, request: Request,
                              user: dict = Depends(get_current_user)):
    require_hmrc()
    if not body.confirm:
        raise HTTPException(status_code=400,
                            detail="Confirm the figures before submitting to HMRC.")
    periods = hmrc_mapping.quarters(body.tax_year)
    chosen = next((q for q in periods if q["quarter"] == body.quarter), None)
    if chosen is None:
        raise HTTPException(status_code=400, detail="That quarter is not part of this tax year.")

    connection = await hmrc_service.require_connection(user["id"])
    async with pool.tenant(user["id"]) as conn:
        invoices = await repo.list_invoices(conn)
        expenses = await repo.list_expenses(conn)
        category_records = await repo.expense_categories(conn)
    payload = hmrc_mapping.build_cumulative_payload(
        invoices=invoices, expenses=expenses, categories=category_records,
        period_start=date.fromisoformat(chosen["period_start"]),
        period_end=date.fromisoformat(chosen["period_end"]))
    try:
        status_code, response = await hmrc_service.submit_cumulative(
            user_id=user["id"], connection=connection,
            fraud_headers=device_headers(request, user),
            tax_year=body.tax_year, payload=payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if status_code >= 300:
        raise _hmrc_failure(status_code, response)
    return {"submitted": True, "tax_year": body.tax_year, "quarter": chosen,
            "summary": hmrc_mapping.summarise_payload(payload), "response": response}


@api_router.post("/hmrc/calculation")
async def hmrc_trigger_calculation(request: Request, tax_year: Optional[str] = None,
                                   user: dict = Depends(get_current_user)):
    require_hmrc()
    year = tax_year or hmrc_mapping.tax_year_for(date.today())
    connection = await hmrc_service.require_connection(user["id"])
    try:
        status_code, payload = await hmrc_service.trigger_calculation(
            user_id=user["id"], connection=connection,
            fraud_headers=device_headers(request, user), tax_year=year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if status_code >= 300:
        raise _hmrc_failure(status_code, payload)
    return {"tax_year": year, **(payload or {})}


@api_router.get("/hmrc/calculation/{calculation_id}")
async def hmrc_get_calculation(calculation_id: str, request: Request,
                               tax_year: Optional[str] = None,
                               user: dict = Depends(get_current_user)):
    require_hmrc()
    year = tax_year or hmrc_mapping.tax_year_for(date.today())
    connection = await hmrc_service.require_connection(user["id"])
    status_code, payload = await hmrc_service.retrieve_calculation(
        user_id=user["id"], connection=connection,
        fraud_headers=device_headers(request, user), tax_year=year,
        calculation_id=calculation_id)
    if status_code >= 300:
        raise _hmrc_failure(status_code, payload)
    return payload


@api_router.get("/hmrc/submissions")
async def hmrc_submissions(user: dict = Depends(get_current_user)):
    async with pool.tenant(user["id"]) as conn:
        return {"submissions": await hmrc_repo.list_submissions(conn)}


@api_router.get("/")
async def root():
    return {"message": "PsyBooks API"}


@api_router.get("/health")
async def health():
    """Liveness + readiness probe for the hosting platform and store review."""
    db_ok = await pool.healthy()
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "storage": STORAGE_BACKEND,
        "receipt_ocr": LLM_PROVIDER or "disabled",
        "companies_house": bool(COMPANIES_HOUSE_API_KEY),
        "hmrc": hmrc_client.config().environment if (hmrc_client.enabled() and crypto.available()) else "disabled",
        "time": now_iso(),
    }
    if not db_ok:
        raise HTTPException(status_code=503, detail=body)
    return body


# ---------------------------------------------------------------------------
# Legal pages (privacy / terms / account deletion / support)
# Served from the API host so the store listings always have a live URL.
# ---------------------------------------------------------------------------
LEGAL_DIR = ROOT_DIR / "legal"


@app.get("/legal", include_in_schema=False)
@app.get("/legal/", include_in_schema=False)
async def legal_index():
    return FileResponse(LEGAL_DIR / "index.html")


@app.get("/legal/{page}", include_in_schema=False)
async def legal_page(page: str):
    name = page if page.endswith((".html", ".css")) else f"{page}.html"
    target = (LEGAL_DIR / name).resolve()
    if LEGAL_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Page not found")
    return FileResponse(target)


# HMRC/crypto failures become clear messages rather than 500s.
@app.exception_handler(hmrc_service.NotConnected)
async def _not_connected_handler(request: Request, exc: hmrc_service.NotConnected):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(crypto.EncryptionUnavailable)
async def _encryption_handler(request: Request, exc: crypto.EncryptionUnavailable):
    from fastapi.responses import JSONResponse
    logger.error(f"Encryption unavailable: {exc}")
    return JSONResponse(status_code=503,
                        content={"detail": "HMRC features are unavailable. Please reconnect to HMRC."})


@app.exception_handler(hmrc_client.HMRCError)
async def _hmrc_error_handler(request: Request, exc: hmrc_client.HMRCError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=502, content={"detail": exc.message})


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    # Credentials cannot be combined with a wildcard origin; the app uses a
    # bearer token, not cookies, so credentials stay off unless origins are pinned.
    allow_credentials=CORS_ORIGINS != ["*"],
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)



