# Test Credentials — ASETS

## App
Mini ERP for self-employed UK psychologists. JWT email/password auth.
Backend base: `${EXPO_PUBLIC_BACKEND_URL}/api`

## Test user (register a fresh one, or use)
- Email: `qa@psybooks.com`
- Password: `secret123`
- Name: `Dr QA`

The testing agent may register a fresh account (any email + 6+ char password) via the Register screen or POST /api/auth/register.

## Local development
- Database: PostgreSQL 17. `docker compose up` then `docker compose run --rm api python -m db.deploy`.
- Backend tests boot their own throwaway cluster: `cd backend && python -m pytest` (no setup needed beyond `postgresql@17` on PATH).
- HMRC sandbox: create a test user via HMRC's Create Test User API; use that NINO, never a real one.

## Notes
- Currency GBP. UK fiscal year 6 Apr – 5 Apr.
- No VAT (exempt healthcare services).
- Creating an invoice requires at least one client first (Clients screen, reached via people icon on Home).
