"""Data access. Every SQL statement in the application lives here.

The dictionaries returned by this module are the API's wire format: the
mobile app is already shipping against these field names, so the mapping
from column to key is deliberate and stable — `expenses.expense_date`
becomes `date`, money comes back as a float, dates as ISO strings.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import asyncpg

# ---------------------------------------------------------------------------
# Scalar conversion
# ---------------------------------------------------------------------------


def _money(v: Any) -> float:
    """NUMERIC -> float, at the edge only.

    Arithmetic stays in Decimal/NUMERIC; this runs when the value is on
    its way out to JSON, where a float is what the app expects.
    """
    if v is None:
        return 0.0
    return float(v)


def _opt_money(v: Any) -> Optional[float]:
    return None if v is None else float(v)


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def _parse_date(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _jsonb(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

USER_COLUMNS = """
    id, email, password_hash, name, business_name, address, city, postcode,
    utr, company_reg, vat_number, ni_number,
    bank_name, bank_account_name, bank_sort_code, bank_account_number, bank_reference,
    settings, created_at
"""


def user_dict(row: asyncpg.Record, services: list | None = None) -> dict:
    """The shape the app has always received, rebuilt from columns."""
    return {
        "id": str(row["id"]),
        "email": str(row["email"]),
        "password_hash": row["password_hash"],
        "name": row["name"],
        "business_name": row["business_name"],
        "address": row["address"],
        "city": row["city"],
        "postcode": row["postcode"],
        "utr": row["utr"],
        "company_reg": row["company_reg"],
        "vat_number": row["vat_number"],
        "ni_number": row["ni_number"],
        "bank": {
            "bank_name": row["bank_name"],
            "account_name": row["bank_account_name"],
            "sort_code": row["bank_sort_code"],
            "account_number": row["bank_account_number"],
            "reference": row["bank_reference"],
        },
        "services": services if services is not None else [],
        "settings": _jsonb(row["settings"]),
        "created_at": _iso(row["created_at"]),
    }


async def services_for(conn: asyncpg.Connection, user_id: str) -> list:
    rows = await conn.fetch(
        "SELECT id, name, price, unit FROM asets.user_services WHERE user_id = $1 ORDER BY created_at",
        user_id)
    return [{"id": str(r["id"]), "name": r["name"], "price": _opt_money(r["price"]), "unit": r["unit"]}
            for r in rows]


async def create_user(conn: asyncpg.Connection, *, email: str, password_hash: str, name: str) -> dict:
    row = await conn.fetchrow(
        f"""INSERT INTO asets.users (email, password_hash, name)
            VALUES ($1, $2, $3) RETURNING {USER_COLUMNS}""",
        email, password_hash, name)
    return user_dict(row, [])


async def find_by_email(conn: asyncpg.Connection, email: str) -> Optional[dict]:
    row = await conn.fetchrow(
        f"SELECT {USER_COLUMNS} FROM asets.users WHERE lower(email) = lower($1) AND deleted_at IS NULL",
        email)
    return user_dict(row, []) if row else None


async def get_user(conn: asyncpg.Connection, user_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        f"SELECT {USER_COLUMNS} FROM asets.users WHERE id = $1 AND deleted_at IS NULL", user_id)
    if not row:
        return None
    return user_dict(row, await services_for(conn, user_id))


# Profile fields that map one-to-one onto a column.
_PROFILE_COLUMNS = ("name", "business_name", "address", "city", "postcode", "utr",
                    "company_reg", "vat_number", "ni_number")
_BANK_KEYS = {"bank_name": "bank_name", "account_name": "bank_account_name",
              "sort_code": "bank_sort_code", "account_number": "bank_account_number",
              "reference": "bank_reference"}


async def update_profile(conn: asyncpg.Connection, user_id: str, updates: dict) -> dict:
    sets, args = [], []

    for field in _PROFILE_COLUMNS:
        if updates.get(field) is not None:
            args.append(updates[field])
            sets.append(f"{field} = ${len(args)}")

    if updates.get("bank") is not None:
        for key, column in _BANK_KEYS.items():
            value = updates["bank"].get(key)
            if value is not None:
                args.append(str(value))
                sets.append(f"{column} = ${len(args)}")

    if updates.get("settings") is not None:
        args.append(json.dumps(updates["settings"]))
        sets.append(f"settings = ${len(args)}::jsonb")

    if sets:
        args.append(user_id)
        await conn.execute(
            f"UPDATE asets.users SET {', '.join(sets)} WHERE id = ${len(args)}", *args)

    if updates.get("services") is not None:
        await _replace_services(conn, user_id, updates["services"])

    return await get_user(conn, user_id)


async def _replace_services(conn: asyncpg.Connection, user_id: str, services: list) -> None:
    """The app sends the whole list every time, so replace wholesale.

    Duplicate names are collapsed (last wins) rather than raising: the
    unique index protects the data, but a duplicate here is a UI slip,
    not something worth failing the user's save over.
    """
    await conn.execute("DELETE FROM asets.user_services WHERE user_id = $1", user_id)
    seen: dict[str, dict] = {}
    for svc in services:
        name = str(svc.get("name", "")).strip()
        if not name:
            continue
        seen[name.lower()] = svc
    for svc in seen.values():
        price = svc.get("price")
        unit = svc.get("unit") or "session"
        if unit not in ("session", "hour", "fixed"):
            unit = "session"
        await conn.execute(
            """INSERT INTO asets.user_services (user_id, name, price, unit)
               VALUES ($1, $2, $3, $4::asets.service_unit)""",
            user_id, str(svc["name"]).strip(),
            Decimal(str(price)) if price not in (None, "") else None, unit)


async def delete_account(conn: asyncpg.Connection, user_id: str) -> None:
    """Hard delete. Every child row cascades, including the HMRC audit
    trail — which is why this runs under pool.privileged()."""
    await conn.execute("DELETE FROM asets.users WHERE id = $1", user_id)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

def client_dict(row: asyncpg.Record) -> dict:
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "name": row["name"],
        "contact_name": row["contact_name"],
        "email": row["email"],
        "address": row["address"],
        "company_number": row["company_number"],
        "notes": row["notes"],
        "rate": _opt_money(row["rate"]),
        "created_at": _iso(row["created_at"]),
        "deleted_at": _iso(row["deleted_at"]),
    }


CLIENT_COLUMNS = ("id, user_id, name, contact_name, email, address, company_number, "
                  "notes, rate, created_at, deleted_at")


async def list_clients(conn: asyncpg.Connection) -> list:
    rows = await conn.fetch(
        f"SELECT {CLIENT_COLUMNS} FROM asets.clients WHERE deleted_at IS NULL ORDER BY name")
    return [client_dict(r) for r in rows]


async def create_client(conn: asyncpg.Connection, user_id: str, body: dict) -> dict:
    row = await conn.fetchrow(
        f"""INSERT INTO asets.clients
              (user_id, name, contact_name, email, address, company_number, notes, rate)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            RETURNING {CLIENT_COLUMNS}""",
        user_id, body["name"], body.get("contact_name", ""), body.get("email", ""),
        body.get("address", ""), body.get("company_number", ""), body.get("notes", ""),
        Decimal(str(body["rate"])) if body.get("rate") is not None else None)
    return client_dict(row)


async def update_client(conn: asyncpg.Connection, client_id: str, body: dict) -> Optional[dict]:
    row = await conn.fetchrow(
        f"""UPDATE asets.clients
               SET name = $2, contact_name = $3, email = $4, address = $5,
                   company_number = $6, notes = $7, rate = $8
             WHERE id = $1 AND deleted_at IS NULL
            RETURNING {CLIENT_COLUMNS}""",
        client_id, body["name"], body.get("contact_name", ""), body.get("email", ""),
        body.get("address", ""), body.get("company_number", ""), body.get("notes", ""),
        Decimal(str(body["rate"])) if body.get("rate") is not None else None)
    return client_dict(row) if row else None


async def soft_delete_client(conn: asyncpg.Connection, client_id: str) -> None:
    await conn.execute(
        "UPDATE asets.clients SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL",
        client_id)


async def client_name_map(conn: asyncpg.Connection) -> dict:
    rows = await conn.fetch("SELECT id, name FROM asets.clients")
    return {str(r["id"]): r["name"] for r in rows}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

INVOICE_SELECT = """
SELECT i.id, i.user_id, i.client_id, i.number, i.issue_date, i.due_date, i.status,
       i.notes, i.total, i.paid_date, i.created_at, i.deleted_at,
       c.name AS client_name,
       COALESCE(
           (SELECT json_agg(json_build_object(
                       'description', it.description,
                       'quantity', it.quantity,
                       'unit_price', it.unit_price)
                    ORDER BY it.position)
              FROM asets.invoice_items it WHERE it.invoice_id = i.id),
           '[]'::json) AS items
  FROM asets.invoices i
  JOIN asets.clients c ON c.id = i.client_id
"""


def invoice_dict(row: asyncpg.Record) -> dict:
    items = _jsonb(row["items"]) or []
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "client_id": str(row["client_id"]),
        "client_name": row["client_name"] or "Unknown client",
        "number": row["number"],
        "issue_date": _iso(row["issue_date"]),
        "due_date": _iso(row["due_date"]),
        "status": row["status"],
        "notes": row["notes"],
        "items": [{"description": it["description"],
                   "quantity": float(it["quantity"]),
                   "unit_price": float(it["unit_price"])} for it in items],
        "total": _money(row["total"]),
        "paid_date": _iso(row["paid_date"]),
        "created_at": _iso(row["created_at"]),
        "deleted_at": _iso(row["deleted_at"]),
    }


async def list_invoices(conn: asyncpg.Connection) -> list:
    rows = await conn.fetch(
        INVOICE_SELECT + " WHERE i.deleted_at IS NULL ORDER BY i.issue_date DESC, i.created_at DESC")
    return [invoice_dict(r) for r in rows]


async def get_invoice(conn: asyncpg.Connection, invoice_id: str) -> Optional[dict]:
    row = await conn.fetchrow(INVOICE_SELECT + " WHERE i.id = $1 AND i.deleted_at IS NULL", invoice_id)
    return invoice_dict(row) if row else None


async def _next_invoice_number(conn: asyncpg.Connection, user_id: str) -> str:
    """INV-0001, INV-0002, ... per user.

    The advisory lock serialises two devices creating an invoice at the
    same instant; the unique index is the backstop if it ever escapes.
    """
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", str(user_id))
    highest = await conn.fetchval(
        """SELECT COALESCE(MAX(NULLIF(regexp_replace(number, '\\D', '', 'g'), '')::bigint), 0)
             FROM asets.invoices WHERE user_id = $1""",
        user_id)
    return f"INV-{int(highest) + 1:04d}"


async def create_invoice(conn: asyncpg.Connection, user_id: str, body: dict) -> dict:
    number = await _next_invoice_number(conn, user_id)
    status = body.get("status", "sent")
    paid_date = date.today() if status == "paid" else None
    row = await conn.fetchrow(
        """INSERT INTO asets.invoices
             (user_id, client_id, number, issue_date, due_date, status, notes, paid_date)
           VALUES ($1,$2,$3,$4,$5,$6::asets.invoice_status,$7,$8)
           RETURNING id""",
        user_id, body["client_id"], number, _parse_date(body["issue_date"]),
        _parse_date(body.get("due_date")), status, body.get("notes", ""), paid_date)
    await _replace_items(conn, str(row["id"]), user_id, body.get("items") or [])
    return await get_invoice(conn, str(row["id"]))


async def _replace_items(conn: asyncpg.Connection, invoice_id: str, user_id: str, items: list) -> None:
    await conn.execute("DELETE FROM asets.invoice_items WHERE invoice_id = $1", invoice_id)
    for position, item in enumerate(items, start=1):
        await conn.execute(
            """INSERT INTO asets.invoice_items
                 (invoice_id, user_id, position, description, quantity, unit_price)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            invoice_id, user_id, position, item.get("description", ""),
            Decimal(str(item.get("quantity", 1))), Decimal(str(item.get("unit_price", 0))))


async def update_invoice(conn: asyncpg.Connection, invoice_id: str, user_id: str, updates: dict) -> Optional[dict]:
    current = await conn.fetchrow(
        "SELECT status, paid_date FROM asets.invoices WHERE id = $1 AND deleted_at IS NULL", invoice_id)
    if current is None:
        return None

    sets, args = [], []

    def add(fragment: str, value: Any) -> None:
        args.append(value)
        sets.append(fragment.format(n=len(args)))

    if updates.get("client_id") is not None:
        add("client_id = ${n}", updates["client_id"])
    if updates.get("issue_date") is not None:
        add("issue_date = ${n}", _parse_date(updates["issue_date"]))
    if updates.get("due_date") is not None:
        add("due_date = ${n}", _parse_date(updates["due_date"]))
    if updates.get("notes") is not None:
        add("notes = ${n}", updates["notes"])

    if updates.get("status") is not None:
        status = updates["status"]
        add("status = ${n}::asets.invoice_status", status)
        # The database refuses a paid invoice with no paid_date, so the
        # two always move together.
        if status == "paid":
            paid = _parse_date(updates.get("paid_date")) or current["paid_date"] or date.today()
            add("paid_date = ${n}", paid)
        else:
            sets.append("paid_date = NULL")
    elif updates.get("paid_date") is not None and current["status"] == "paid":
        add("paid_date = ${n}", _parse_date(updates["paid_date"]))

    if sets:
        args.append(invoice_id)
        await conn.execute(
            f"UPDATE asets.invoices SET {', '.join(sets)} WHERE id = ${len(args)}", *args)

    if updates.get("items") is not None:
        await _replace_items(conn, invoice_id, user_id, updates["items"])

    return await get_invoice(conn, invoice_id)


async def soft_delete_invoice(conn: asyncpg.Connection, invoice_id: str) -> None:
    await conn.execute(
        "UPDATE asets.invoices SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL",
        invoice_id)


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

EXPENSE_COLUMNS = ("id, user_id, category, description, amount, expense_date, "
                   "receipt_path, created_at, deleted_at")


def expense_dict(row: asyncpg.Record) -> dict:
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "category": row["category"],
        "description": row["description"],
        "amount": _money(row["amount"]),
        # The app has always called this "date".
        "date": _iso(row["expense_date"]),
        "receipt_path": row["receipt_path"],
        "created_at": _iso(row["created_at"]),
        "deleted_at": _iso(row["deleted_at"]),
    }


async def list_expenses(conn: asyncpg.Connection) -> list:
    rows = await conn.fetch(
        f"""SELECT {EXPENSE_COLUMNS} FROM asets.expenses
             WHERE deleted_at IS NULL ORDER BY expense_date DESC, created_at DESC""")
    return [expense_dict(r) for r in rows]


async def create_expense(conn: asyncpg.Connection, user_id: str, body: dict) -> dict:
    row = await conn.fetchrow(
        f"""INSERT INTO asets.expenses
              (user_id, category, description, amount, expense_date, receipt_path)
            VALUES ($1,$2,$3,$4,$5,$6) RETURNING {EXPENSE_COLUMNS}""",
        user_id, body["category"], body.get("description", ""),
        Decimal(str(body["amount"])), _parse_date(body["date"]), body.get("receipt_path"))
    return expense_dict(row)


async def update_expense(conn: asyncpg.Connection, expense_id: str, body: dict) -> Optional[dict]:
    row = await conn.fetchrow(
        f"""UPDATE asets.expenses
               SET category = $2, description = $3, amount = $4,
                   expense_date = $5, receipt_path = $6
             WHERE id = $1 AND deleted_at IS NULL
            RETURNING {EXPENSE_COLUMNS}""",
        expense_id, body["category"], body.get("description", ""),
        Decimal(str(body["amount"])), _parse_date(body["date"]), body.get("receipt_path"))
    return expense_dict(row) if row else None


async def soft_delete_expense(conn: asyncpg.Connection, expense_id: str) -> None:
    await conn.execute(
        "UPDATE asets.expenses SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL",
        expense_id)


async def expense_categories(conn: asyncpg.Connection) -> list:
    """The single source of truth for categories.

    The app's picker, the receipt-reading prompt and the HMRC submission
    all read this. They used to be three separate hardcoded lists, which
    is how a client dinner ended up declared as an allowable expense.
    """
    rows = await conn.fetch(
        """SELECT code, label, icon, hint, hmrc_field, disallowable
             FROM asets.expense_categories ORDER BY position""")
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Receipt images (STORAGE_BACKEND=postgres)
# ---------------------------------------------------------------------------

async def put_receipt(conn: asyncpg.Connection, *, path: str, user_id: str,
                      data: bytes, content_type: str) -> dict:
    await conn.execute(
        """INSERT INTO asets.receipt_files (path, user_id, content_type, bytes)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (path) DO UPDATE SET bytes = EXCLUDED.bytes,
                                            content_type = EXCLUDED.content_type""",
        path, user_id, content_type, data)
    return {"path": path, "size": len(data)}


async def get_receipt(conn: asyncpg.Connection, path: str) -> Optional[tuple]:
    row = await conn.fetchrow(
        "SELECT bytes, content_type FROM asets.receipt_files WHERE path = $1", path)
    if row is None:
        return None
    return bytes(row["bytes"]), row["content_type"]
