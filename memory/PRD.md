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
- Backend 39/39 pytest passing; frontend verified.

## Tax logic
2024/25 England rates. Personal allowance £12,570 (tapered >£100k), basic 20% / higher 40% / additional 45%; NI Class 4: 6% (£12,570–£50,270), 2% above. No VAT.

## Backlog / next
- P1: Email invoice directly; invoice editing; recurring invoices; per-client invoice history.
- P1: Payments-received tracking (cash-basis toggle sales vs paid) for HMRC.
- P2: Mileage/simplified-expense helpers; export CSV for accountant.
- P2: Reorder dashboard cards by drag; Welsh/Scottish tax bands.
