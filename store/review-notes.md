# Reviewer notes (paste into both consoles)

Seed the demo account first — an empty account shows none of the features:

```bash
python3 scripts/seed_demo.py https://<your-api-host> reviewer@asets.app 'Review2026!'
```

Then use the text below.

---

## App Store Connect → App Review Information → Notes

```
ASETS is a bookkeeping app for self-employed practitioners in the UK. An account
is required because every invoice, expense and tax figure belongs to the signed-in
user; there is no content to show without one.

DEMO ACCOUNT
  Email:    reviewer@asets.app
  Password: Review2026!
The account is pre-populated with two clients, four invoices and six expenses.

WHAT TO TRY
1. Home — take-home estimate, Self Assessment estimate, cash-flow chart.
2. Invoices tab — open an invoice, "Share PDF" opens the native share sheet.
3. Expenses tab — "+" then "Scan receipt" uses the camera (permission prompt).
   Photographing any receipt fills the amount, date and merchant automatically.
   The expense can also be typed in by hand.
4. Tax tab — choose a tax year or a custom range; "Export CSV for accountant".
5. Settings (gear on Home) — theme, Face ID app lock, business details.

ACCOUNT DELETION (Guideline 5.1.1(v))
  Settings → Delete account → "Yes, delete my account".
  It deletes the account and all data immediately. Web page for users who have
  uninstalled the app: https://<your-api-host>/legal/delete-account

PERMISSIONS
  Camera / Photos — only to attach a receipt to an expense; both are optional.
  Face ID — optional app lock, off by default. Biometric checks happen on device;
  the app receives only a pass/fail result.

HMRC FILING (if enabled in this build)
Settings -> HMRC. The user signs in on HMRC's own website; ASETS never sees
their Government Gateway password. Nothing is sent to HMRC until the user
reviews the figures on screen and confirms. The demo account is connected to
HMRC's sandbox, which contains test data only - no real tax record is touched.

NOT A FINANCIAL SERVICE
The app does not process payments, hold funds, or connect to any bank. It
produces an estimate of Income Tax and National Insurance from figures the user
types in, and files nothing with HMRC. It is not affiliated with HMRC.

Support: ops@axisbsolutions.com
```

## Play Console → App content → App access

Select **"All or some functionality is restricted"** and add one instruction set:

| Field | Value |
|---|---|
| Name | Demo account |
| Username | `reviewer@asets.app` |
| Password | `Review2026!` |
| Any other instructions | Sign in on the first screen. The account is pre-populated with clients, invoices and expenses. Account deletion: Settings (gear icon on Home) → Delete account. Camera permission is only used for the optional "Scan receipt" flow on the Expenses tab. |

---

## Rejection risks and the honest answer to each

| Risk | Response |
|---|---|
| "Looks like a financial service / tax filing app" | It calculates an estimate from user-entered data and files nothing. Wording is in the review notes and the listing. |
| "Implies affiliation with HMRC" | Never use the HMRC logo or crest. Keep the phrase "estimate" in screenshots and listing copy. |
| Guideline 5.1.1(v) — account deletion | Implemented in-app plus a public web page. |
| Guideline 4.2 — minimum functionality | The app is a full bookkeeping tool, not a web wrapper. Point the reviewer at the five flows above. |
| Play — Data safety mismatch | The form answers in `store/play-data-safety.md` match the privacy policy exactly. Keep them in sync if the app changes. |
| Camera permission questioned | Declared purpose strings are specific to receipts; the feature is optional and reachable in two taps for the reviewer to see. |
| "Why does it collect a device identifier?" | Making Tax Digital legally requires fraud prevention headers identifying the submitting device. It is a random per-install UUID, sent only to HMRC, never used for tracking. Explained in the privacy policy under "Connecting to HMRC". |
| "Does this imply an HMRC partnership?" | No. The app uses HMRC's public API with the user's consent. Never show the HMRC logo or crest. |
