# PsyBooks — PRD

## Original problem statement
Mobile Mini ERP for self-employed UK psychologists (teleconsultations). Manage a few clients (companies that contract them on receipts), register invoices and share as PDF, track cash flow, log profession-related expenses, and get an HMRC Self Assessment estimate (sales, expenses, tax to pay). No VAT (exempt healthcare). "Apple-style" design on Android. Built for people with ADHD and low financial literacy → very easy to navigate, cards/widgets, customizable.

## User choices
- Auth: email/password (JWT).
- PDF: generate + share via native share sheet (email/WhatsApp).
- Tax: income-tax band estimate + National Insurance (Class 4).
- Period: preset fiscal years + custom date range; result on a receipt canvas with PDF download + copy-paste.
- Theme: light / dark / system, minimalist iOS style.
- Customizable dashboard cards.

## Architecture
- Backend: FastAPI + Motor (MongoDB), JWT (pyjwt) + bcrypt. Routes under `/api`. Soft deletes (`deleted_at`). UUID string ids.
- Frontend: Expo Router (file-based), React Native. ThemeProvider (light/dark/system tokens from design_guidelines), AuthContext, Toast, @gorhom/bottom-sheet, react-native-keyboard-controller, expo-print + expo-sharing (PDF), expo-clipboard, @react-native-community/datetimepicker.
- Design: "iOS-Native Clean" — sage green #5F7161 brand, terracotta #D27D56 accent, Space Grotesk (numbers) + Plus Jakarta Sans (text).

## Data models
- User (email, password_hash, name, business_name, address, utr, settings{theme, cards})
- Client (name, contact_name, email, address, rate)
- Invoice (number auto INV-000N, client_id, issue_date, due_date, items[], total, status draft/sent/paid, notes)
- Expense (category, description, amount, date)

## Implemented (2026-06-28)
- Email/password register + login, JWT, session bootstrap, logout.
- Dashboard: take-home widget, HMRC estimate, cash-flow mini bar chart, paid vs outstanding, quick add, customizable cards.
- Clients CRUD (bottom sheet).
- Invoices CRUD, line items, live total, status, PDF share, mark paid.
- Expenses CRUD, categories tailored to psychologists.
- Tax canvas: preset fiscal years + custom range, income-tax bands + NI Class 4, PDF export + copy text.
- Settings: theme light/dark/system, dashboard card toggles, business profile (used on invoices).
- Backend 17/17 pytest passing; frontend E2E validated.

## Iteration 2 (2026-06-28)
- Email invoice: POST /api/invoices/{id}/email via Emergent-managed Resend (from_name=PsyBooks, reply-to=psychologist, recipient=client's stored email, server-side HTML template, guardrail gate). "Send by email" button in invoice detail (shown only when client has email).
- Payments: invoices carry paid_date (set on mark-paid, cleared on revert). New /payments screen — total owed, owed grouped by client with quick mark-paid, recently-paid list. Reached from Dashboard Payments card.
- Edit invoice: detail sheet "Edit" reopens the form prefilled; PUT persists client/dates/items/notes/status and recomputes total.
- Export CSV: GET /api/export/csv?start=&end= (INCOME with client names, EXPENSES, SUMMARY). "Export CSV for accountant" button on Tax tab; shares file (native) / downloads (web).
## Iteration 3 (2026-06-28)
- Send-confirmation: POST /api/invoices/{id}/email now records emailed_at and auto-marks a draft as "sent"; invoice detail caption shows "Emailed {date}".
- Receipt photo → AI expense: expo-image-picker (camera + gallery) → POST /api/expenses/scan; image stored in Emergent Object Storage (psybooks/uploads/{user_id}/...), Gemini 3 Flash (gemini-3-flash-preview) extracts amount/currency/date/merchant/description/category. GET /api/files/{path}?token= serves owner-only. Expense stores receipt_path; list shows receipt thumbnail (expo-image).
- Cash flow Day/Week/Month/Year: dashboard segmented control; /api/summary?group=day|week|month returns net + bucketed cashflow; hero + cash-flow card update per period. HMRC card stays annual (fiscal year) by design.
- Biometric app-lock: expo-local-authentication (Face ID/fingerprint). BiometricProvider gates the app when enabled (lock overlay, re-auth on foreground), auto-prompts once to configure, Settings toggle. app.json permissions/plugins added (camera, photo library, Face ID, USE_BIOMETRIC). Device-only (Expo Go on a real device / build) — no-op on web preview.
## Iteration 4 — Rebrand to ASETS (2026-06-28, frontend visual only)
- Official name: ASETS (ADHD Self-Employed Taxes Support). Backend code unchanged.
- New logo (src/components/Logo.tsx, react-native-svg): Hinomaru red circle (#BC002D) + soft-blue ring (#8CAFD6) + white ascending check — Japanese, minimal, empowering ("done, moving forward").
- Regenerated app assets (icon, adaptive-icon, splash, favicon) to match logo; splash/adaptive bg white; app.json name = ASETS.
- New palette in tokens.ts: whites + soft blues (#3E6FA8 primary) + Hinomaru red (#BC002D accent for tax/attention). Light + dark.
## Iteration 5 — Invoice auto-fill, services & Companies House (2026-06-28)
- Profile expanded: city, postcode, company_reg, vat_number, ni_number, bank{bank_name,account_name,sort_code,account_number,reference}, services[]. Returned by /auth/me + /auth/profile.
- Settings: "Your details" (city/postcode/Company Reg/VAT/UTR), "Payment details" card (bank + reference default "Please use the invoice number"), "Your services" manager (name/price/unit session|hour|fixed).
- Invoices: per-line "Choose a service" searchable picker (src/data/services.ts psychology catalogue + user's saved services) → fills description + price.
- Clients: "Find on Companies House" → backend proxy GET /api/companies/search + /api/companies/{number} (HTTP Basic w/ COMPANIES_HOUSE_API_KEY) auto-fills name + registered address + company_number. Graceful 503 when key not configured. Client model stores company_number.
- Invoice PDF: company header (Company Reg / VAT No / city+postcode) + PAYMENT DETAILS block from saved bank details.
- Backend 48/48 pytest passing; frontend verified. NOTE: Companies House needs a free API key (COMPANIES_HOUSE_API_KEY in backend/.env) — company lookup returns a graceful "not configured" message until set.

## Iteration 6 — Store launch readiness (2026-08-28)
- Backend made self-hostable: storage backend (`STORAGE_BACKEND=local|emergent`, local disk volume), vision provider (`LLM_PROVIDER=anthropic|emergent`, Claude vision + JSON schema), email provider (`EMAIL_PROVIDER=resend|emergent`). Each degrades with a clear 503 when unconfigured. `requirements-prod.txt` drops `emergentintegrations`.
- New endpoints: `GET /api/health` (db ping + which features are configured), `DELETE /api/auth/account` (hard delete of user + clients/invoices/expenses + receipts — required by both stores).
- CORS now env-driven (`CORS_ORIGINS`); credentials only enabled when origins are pinned.
- Legal pages served by the API at `/legal/{privacy,terms,delete-account,support}` (`backend/legal/`), so store listings always have live URLs.
- Deploy configs: `backend/Dockerfile`, `backend/fly.toml`, `render.yaml`, `docker-compose.yml`.
- Frontend: `app.json` rewritten for release (name ASETS, slug asets, scheme asets, bundle id `com.axisbsolutions.asets`, export-compliance flag, blockedPermissions, dark splash); `eas.json` with development/preview/production + submit profiles; Settings gained Legal & support links, in-app account deletion and a version footer; `src/config/app.ts` centralises backend/legal URLs.
- Docs: `LAUNCH.md` runbook, `store/` (listing copy, Play data safety, Apple privacy labels, review notes, screenshots, checklist), `scripts/preflight.sh`, `scripts/seed_demo.py`.
- Verified: expo-doctor 18/18, tsc clean, `expo prebuild` android manifest correct, API imports + serves legal pages with prod deps only.

## Iteration 7 — PostgreSQL, HMRC MTD and Cloud Run (2026-08-28)
- **Database rewritten from MongoDB to PostgreSQL 17** (`backend/db/`). Schema `asets`, numbered immutable SQL migrations (`db/migrations/0001_init`, `0002_hmrc`, `0003_grants`), runner `db/migrate.py`, deploy-time job `db/deploy.py` (creates the `asets_app` role + applies migrations, idempotent). Data access consolidated in `db/repo.py` / `db/hmrc_repo.py`; API wire shapes unchanged so the shipped app keeps working.
- Money is `NUMERIC(12,2)`; `invoice_items.line_total` is a generated column and `invoices.total` is maintained by trigger. Check constraints (paid ⇒ paid_date, due ≥ issue, non-negative amounts), FK on expense categories, unique invoice number per user (advisory-lock allocation).
- **Row-level security** on every tenant table with `FORCE`; `asets.current_user_id()` reads a transaction-local setting set by `pool.tenant()`. `users` and `hmrc_oauth_states` are excluded by design (login and the OAuth callback resolve identity themselves). Runtime role `asets_app` has DML only, no DDL, read-only on the category lookup.
- **HMRC Making Tax Digital for Income Tax** (`backend/hmrc/`): OAuth2 connect/callback with single-use state, token refresh in its own transaction (HMRC rotates refresh tokens), Business Details v2.0, Obligations v3.0, Self Employment Business v5.0 cumulative quarterly update, Individual Calculations v8.0. Fraud prevention headers for MOBILE_APP_VIA_SERVER built from an `X-ASETS-Device` blob the app sends. Append-only audit trail in `hmrc_submissions` (trigger-enforced; purgeable only by account deletion). Tokens and NINO encrypted with Fernet (`crypto.py`). Final declaration deliberately out of scope.
- Frontend: `app/hmrc.tsx` (connect → NINO → business → quarter preview → confirm → submit → history), `src/utils/device.ts` (device facts for the fraud headers, expo-device + expo-network), HMRC card in Settings.
- **Cloud Run deployment**: `scripts/provision_gcp.sh` (Cloud SQL + Artifact Registry + GCS receipt bucket + service account + Secret Manager), `scripts/deploy_cloudrun.sh` (build → migration job → deploy → health check), `scripts/gen_secrets.py`, `scripts/provision_db.py`. Fly.io/Render configs removed.
- Tests: 75 passing (`backend/tests/`) against a real throwaway PostgreSQL cluster booted per xdist worker — schema constraints, triggers, RLS isolation, audit immutability, full API contract, tenant isolation, reporting maths, and HMRC (mocked transport, asserting URLs, versions, fraud headers and payloads). Old live-server suites moved to `backend/tests/live/` behind `ASETS_LIVE_TESTS=1`.
- Docs: `docs/DATABASE.md`, `docs/HMRC.md`, rewritten `LAUNCH.md`. Privacy policy and terms updated for NINO storage, HMRC submission and fraud-prevention data; store data-safety answers updated.

## Iteration 8 — Free single-client deployment (2026-08-29)
- Target changed from "app stores" to "one client, zero cost". Cloud SQL (~£20/mo) and the GCS receipt bucket were dropped.
- **Database: Supabase free tier.** Currently the `asets` schema inside the existing `axis-builder` project (`aesdrxhezmksxntsnvam`, eu-west-1) — the org's 2-project free limit was already reached, so a dedicated project was not possible. Namespaced schema + own `asets_app` role, nothing else in that database is visible to it. Move path documented in LAUNCH.md §2 (user is creating a separate Supabase account).
- **citext dependency removed** — case-insensitive email uniqueness is now a `UNIQUE INDEX ON lower(email)`, so the schema needs no extensions and runs on any managed Postgres.
- **Receipt images moved into the database** (`asets.receipt_files`, migration 0004, RLS + 8 MB per-row cap + `receipt_storage_usage` view). `STORAGE_BACKEND=postgres` is now the default; storage dispatch became async. Removes the object store and makes account deletion cascade.
- **Cloud Run live**: https://asets-api-7kd7b2l4kq-nw.a.run.app (europe-west2, min-instances=0, ~80 ms warm response). `scripts/provision_gcp.sh` now only creates Artifact Registry + service account + secrets, and grants Cloud Build `artifactregistry.writer` (its absence was the first deploy failure).
- **Two production bugs found by deploying**: (1) `db.deploy` reset the `asets_app` password on every deploy, and Supabase's pooler caches credentials — a routine deploy left the API unable to authenticate. Rotation is now explicit (`DB_ROTATE_PASSWORD=1`). (2) A provider named in the environment without its API key reported as configured and failed mid-request; `_resolve_provider` now treats a missing key as disabled. Both covered by tests.
- `pool.connect()` retries with backoff (scale-to-zero cold starts, pooler hiccups).
- Docs consolidated: new short README.md, LAUNCH.md rewritten for the free path, `scripts/provision_db.py` deleted. 88 tests passing.

## Iteration 9 — HMRC credentials wired (2026-08-29)
- Sandbox credentials configured, stored in Secret Manager and deployed; `/api/health` reports `hmrc: sandbox`.
- Verified against the real HMRC sandbox: credentials valid in sandbox and rejected in production (as expected — production needs HMRC approval). The four APIs ASETS calls are **subscribed** and the pinned versions accepted: Business Details 2.0, Obligations 3.0, Self Employment Business 5.0, Individual Calculations 8.0. Create Test User 1.0 is NOT subscribed (optional).
- **Blocker found**: the redirect URI `https://asets-api-7kd7b2l4kq-nw.a.run.app/api/hmrc/callback` is not registered on the HMRC application — the sign-in step returns `redirect_uri is invalid`. Only fixable in the Developer Hub UI.
- New `scripts/check_hmrc.py`: read-only diagnostic (credential validity + environment, per-API subscription probe using the 403 RESOURCE_FORBIDDEN vs 401 distinction, redirect-URI registration check). Wired into `scripts/preflight.sh`.
- `.mcp.json` added for the new Supabase project (`bmxytncvoancaakryjkw`, aws-1-eu-west-1); it still needs interactive OAuth (`claude /mcp`) plus a session restart. Not a blocker — `scripts/switch_database.py` moves the database without MCP.

## Iteration 9b — HMRC setup complete (2026-08-29)
- Redirect URI registered; `scripts/check_hmrc.py` now passes end to end (credentials sandbox-valid, four APIs subscribed at pinned versions, redirect URI accepted).
- Developer Hub "Customer usage information" fields point at the API's own pages: `/legal/privacy` and `/legal/terms`.
- **18-month grant length handled**: a refresh that fails with `invalid_grant` is now `GrantExpired` (subclass of `NotConnected`) → HTTP 409 "Reconnect in Settings → HMRC", with the reason recorded on the connection and shown on the HMRC screen. An HMRC 5xx is explicitly *not* treated as an expired grant (stays 502). Three tests cover the distinction.
- 91 tests passing.

## Iteration 10 — fraud prevention headers validated (2026-08-29)
- Subscriptions corrected on the Developer Hub: added Business Details 2.0, Obligations 3.0, Individual Calculations 8.0, Create Test User 1.0, Test Fraud Prevention Headers 1.0; removed VAT (MTD), Check a UK VAT number, BSAS and Trader Goods Profiles (HMRC withholds production credentials if you subscribe to APIs you do not use).
- **Correction to iteration 9**: the earlier "subscribed" verdict for the four user-restricted APIs was unsound — HMRC returns 401 before checking subscription when given an application token, so only the application-restricted Create Test User probe was meaningful. `check_hmrc.py` no longer implies otherwise.
- Sandbox test user created (`scripts/hmrc_test_user.py`, output git-ignored).
- **Ran the real headers through HMRC's validator and fixed 3 errors**: `Gov-Vendor-Forwarded` was sending a hostname in `by=` (must be an IP, both halves); `Gov-Vendor-Public-IP` was never set. Cloud Run has no fixed egress IP, so the API now resolves its own address at startup and caches it — no paid static IP needed. `Gov-Client-Multi-Factor` is now reported when the biometric app lock is on (frontend `device.ts`). Result: INVALID_HEADERS (3 errors) → no errors, spec 3.3, 17 headers.
- `Gov-Vendor-License-IDs` deliberately omitted — ASETS has no licence keys; HMRC's sanctioned route is omission plus explanation, wording drafted in docs/HMRC.md.
- Header validation folded into `scripts/check_hmrc.py`.

## Tax logic
2024/25 England rates. Personal allowance £12,570 (tapered >£100k), basic 20% / higher 40% / additional 45%; NI Class 4: 6% (£12,570–£50,270), 2% above. No VAT.

## Backlog / next
- P1: Email invoice directly; invoice editing; recurring invoices; per-client invoice history.
- P1: Payments-received tracking (cash-basis toggle sales vs paid) for HMRC.
- P2: Mileage/simplified-expense helpers; export CSV for accountant.
- P2: Reorder dashboard cards by drag; Welsh/Scottish tax bands.
