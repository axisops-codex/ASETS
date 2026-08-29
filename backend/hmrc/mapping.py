"""Turn ASETS bookkeeping into the payloads HMRC expects.

Two things live here: the UK tax calendar (which is not a calendar year,
and whose quarters start on the 6th), and the translation from our
expense categories to HMRC's self-employment expense fields.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

TAX_YEAR_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _q(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# The UK tax calendar
# ---------------------------------------------------------------------------

def tax_year_for(day: date) -> str:
    """'2026-27' for anything from 6 April 2026 to 5 April 2027."""
    start_year = day.year if (day.month, day.day) >= (4, 6) else day.year - 1
    return f"{start_year}-{str(start_year + 1)[2:]}"


def tax_year_bounds(tax_year: str) -> tuple[date, date]:
    m = TAX_YEAR_RE.match(tax_year)
    if not m:
        raise ValueError(f"tax year must look like 2026-27, got {tax_year!r}")
    start_year = int(m.group(1))
    if int(m.group(2)) != (start_year + 1) % 100:
        raise ValueError(f"{tax_year} is not a consecutive pair of years")
    return date(start_year, 4, 6), date(start_year + 1, 4, 5)


def quarters(tax_year: str) -> list[dict]:
    """The four standard quarterly update periods, with HMRC's due dates.

    Each quarterly update is cumulative: it reports 6 April to the end of
    that quarter, not the quarter in isolation.
    """
    start, end = tax_year_bounds(tax_year)
    y = start.year
    ends = [date(y, 7, 5), date(y, 10, 5), date(y + 1, 1, 5), end]
    # Due one month and seven days after the quarter ends.
    dues = [date(y, 8, 7), date(y, 11, 7), date(y + 1, 2, 7), date(y + 1, 5, 7)]
    return [
        {
            "quarter": i + 1,
            "period_start": start.isoformat(),
            "period_end": q_end.isoformat(),
            "due_date": due.isoformat(),
        }
        for i, (q_end, due) in enumerate(zip(ends, dues))
    ]


def current_quarter(tax_year: str, today: Optional[date] = None) -> Optional[dict]:
    """The quarter `today` falls in, or None if outside the tax year."""
    today = today or date.today()
    start, end = tax_year_bounds(tax_year)
    if not (start <= today <= end):
        return None
    for q in quarters(tax_year):
        if today <= date.fromisoformat(q["period_end"]):
            return q
    return None


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------

def _in_period(iso_date: Optional[str], start: date, end: date) -> bool:
    if not iso_date:
        return False
    try:
        d = date.fromisoformat(str(iso_date)[:10])
    except ValueError:
        return False
    return start <= d <= end


def build_cumulative_payload(
    *,
    invoices: Iterable[dict],
    expenses: Iterable[dict],
    categories: Iterable[dict],
    period_start: date,
    period_end: date,
) -> dict:
    """The body for PUT .../cumulative/{taxYear}.

    Turnover is invoiced income in the period — the same accruals basis
    the rest of the app reports on, so the figure the user sees on the
    dashboard is the figure that reaches HMRC.

    Expenses that HMRC does not allow (client entertainment) are reported
    twice, which is how HMRC expects it: once in `periodExpenses`, as
    money that actually left the business, and again in
    `periodDisallowableExpenses`, so it is added back and not deducted
    from the profit. Reporting it only in the first would understate the
    tax due.
    """
    fields = {c["code"]: c["hmrc_field"] for c in categories}
    disallowed = {c["code"] for c in categories if c.get("disallowable")}

    turnover = sum((_q(i.get("total")) for i in invoices
                    if _in_period(i.get("issue_date"), period_start, period_end)),
                   Decimal("0"))

    buckets: dict[str, Decimal] = {}
    disallowable_buckets: dict[str, Decimal] = {}
    for expense in expenses:
        if not _in_period(expense.get("date"), period_start, period_end):
            continue
        code = expense.get("category")
        field = fields.get(code, "otherExpenses")
        amount = _q(expense.get("amount"))
        buckets[field] = buckets.get(field, Decimal("0")) + amount
        if code in disallowed:
            key = f"{field}Disallowable"
            disallowable_buckets[key] = disallowable_buckets.get(key, Decimal("0")) + amount

    payload: dict = {
        "periodDates": {
            "periodStartDate": period_start.isoformat(),
            "periodEndDate": period_end.isoformat(),
        },
        "periodIncome": {"turnover": float(_q(turnover))},
    }
    if buckets:
        payload["periodExpenses"] = {k: float(_q(v)) for k, v in sorted(buckets.items())}
    if disallowable_buckets:
        payload["periodDisallowableExpenses"] = {
            k: float(_q(v)) for k, v in sorted(disallowable_buckets.items())}
    return payload


def summarise_payload(payload: dict) -> dict:
    """A human-readable digest for the confirmation screen — the user has
    to be shown what they are about to declare."""
    income = payload.get("periodIncome", {})
    expenses = payload.get("periodExpenses", {})
    disallowed = payload.get("periodDisallowableExpenses", {})
    total_expenses = sum(Decimal(str(v)) for v in expenses.values()) if expenses else Decimal("0")
    total_disallowed = sum(Decimal(str(v)) for v in disallowed.values()) if disallowed else Decimal("0")
    turnover = Decimal(str(income.get("turnover", 0)))
    return {
        "turnover": float(_q(turnover)),
        "expenses_total": float(_q(total_expenses)),
        "disallowable_total": float(_q(total_disallowed)),
        # What HMRC will actually tax: disallowable costs are added back.
        "profit": float(_q(turnover - total_expenses + total_disallowed)),
        "expense_lines": [{"field": k, "amount": v} for k, v in sorted(expenses.items())],
        "period_start": payload["periodDates"]["periodStartDate"],
        "period_end": payload["periodDates"]["periodEndDate"],
    }
