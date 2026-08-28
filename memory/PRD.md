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

## Tax logic
2024/25 England rates. Personal allowance £12,570 (tapered >£100k), basic 20% / higher 40% / additional 45%; NI Class 4: 6% (£12,570–£50,270), 2% above. No VAT.

## Backlog / next
- P1: Email invoice directly; invoice editing; recurring invoices; per-client invoice history.
- P1: Payments-received tracking (cash-basis toggle sales vs paid) for HMRC.
- P2: Mileage/simplified-expense helpers; export CSV for accountant.
- P2: Reorder dashboard cards by drag; Welsh/Scottish tax bands.
