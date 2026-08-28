# Test Credentials — PsyBooks

## App
Mini ERP for self-employed UK psychologists. JWT email/password auth.
Backend base: `${EXPO_PUBLIC_BACKEND_URL}/api`

## Test user (register a fresh one, or use)
- Email: `qa@psybooks.com`
- Password: `secret123`
- Name: `Dr QA`

The testing agent may register a fresh account (any email + 6+ char password) via the Register screen or POST /api/auth/register.

## Notes
- Currency GBP. UK fiscal year 6 Apr – 5 Apr.
- No VAT (exempt healthcare services).
- Creating an invoice requires at least one client first (Clients screen, reached via people icon on Home).
