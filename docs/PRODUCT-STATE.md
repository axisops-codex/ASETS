# What is real, and what is not

A register of every user-visible capability, taken from the code rather
than from intent. Written before further changes so nothing gets lost or
silently reworked.

Read the **State** column as: does a user tapping this get the thing they
expect?

Last audited: 29 August 2026 · API `https://asets-api-7kd7b2l4kq-nw.a.run.app`

## Legend

| | |
|---|---|
| ✅ | Works end to end. Backed by a passing test or verified against the live API. |
| 🔑 | Built and deployed, but inert until an API key is supplied. Shows a clear message, never a crash. |
| 📱 | Works, but only on a real phone — the browser cannot do it. |

---

## Sign in

| Capability | State | Notes |
|---|---|---|
| Register (email + password) | ✅ | Email normalised to lowercase; duplicates rejected with 409; passwords under 6 characters rejected |
| Sign in / sign out | ✅ | JWT, 30 days, stored in the device keychain |
| Session survives a restart | ✅ | Token reloaded from secure storage on boot |
| Delete account | ✅ | Erases profile, clients, invoices, expenses, receipts, HMRC tokens and audit trail. Required by both app stores. |

## Dashboard

| Capability | State | Notes |
|---|---|---|
| Period selector (day / week / month / year) | ✅ | Re-queries `/api/summary` with the chosen grouping |
| Estimated take-home | ✅ | Sales − expenses − estimated tax |
| Cash-flow chart | ✅ | Bucketed server-side; verified against seeded data |
| Self Assessment estimate | ✅ | England & NI bands, Class 4 NI. Tested across band boundaries. |
| Paid vs outstanding → Payments | ✅ | |
| Quick actions (new invoice / add expense) | ✅ | Navigate with `?new=1`, which both screens read and act on |
| Choosing which cards show | ✅ | Persisted in the user's settings |

## Invoices

| Capability | State | Notes |
|---|---|---|
| List, create, edit, delete | ✅ | Soft delete — an accountant may need to explain a gap |
| Automatic numbering | ✅ | `INV-0001` upward, per user, allocated under an advisory lock |
| Line items with live total | ✅ | The total is maintained by a database trigger, so it cannot drift |
| Service picker | ✅ | Built-in psychology catalogue plus the user's saved services |
| Status and mark-paid | ✅ | The database refuses a paid invoice with no paid date |
| Share the PDF | 📱 | Generates the PDF and opens the phone's share sheet — the invoice reaches the client from the practitioner's own address. In a browser it downloads instead. |

## Expenses

| Capability | State | Notes |
|---|---|---|
| List, create, edit, delete | ✅ | |
| Categories | ✅ | Fixed lookup table; an unknown category is a clear 400, not a silent write |
| Photograph a receipt → filled-in expense | 🔑 📱 | Needs `ANTHROPIC_API_KEY`. Without it the API answers 503 and the app tells the user to enter it by hand. Needs a camera, so a real phone. |
| Receipt kept as proof | ✅ | Stored in the database, fenced by row-level security, deleted with the account |

## Tax

| Capability | State | Notes |
|---|---|---|
| Preset tax years and custom ranges | ✅ | |
| Estimate as a shareable receipt | 📱 | Same share-sheet caveat as invoices |
| CSV export for an accountant | ✅ | Income, expenses and summary; out-of-range rows excluded |

## Clients

| Capability | State | Notes |
|---|---|---|
| List, create, edit, delete | ✅ | |
| Find on Companies House | 🔑 | Needs `COMPANIES_HOUSE_API_KEY` — free, from a personal Companies House account; owning a UK company is not required. Without it the API answers 503 and the address is typed by hand. |

## Settings

| Capability | State | Notes |
|---|---|---|
| Light / dark / follow the system | ✅ | |
| Business profile, bank details, services | ✅ | All appear on the invoice PDF |
| Face ID / fingerprint lock | 📱 | Device-only. Also reported to HMRC as a second factor when switched on. |
| Legal and support links | ✅ | Served by the API itself, so they cannot drift from the deployment |

## HMRC — Making Tax Digital

| Capability | State | Notes |
|---|---|---|
| Connect (OAuth) | ✅ | Sandbox. Single-use state, redirect URI registered and verified. |
| National Insurance number | ✅ | Encrypted before it reaches the database |
| Find the business at HMRC | ✅ | Business Details 2.0 |
| Obligations and deadlines | ✅ | Obligations 3.0 |
| Preview a quarter before sending | ✅ | The user sees the exact figures they are about to declare |
| Submit a quarterly update | ✅ | Self Employment Business 5.0, cumulative endpoint |
| HMRC's own calculation | ✅ | Individual Calculations 8.0 |
| History of what was sent | ✅ | Append-only, enforced by database trigger |
| Fraud prevention headers | ✅ | Zero errors against HMRC's own validator, spec 3.3 |
| Final declaration (year end) | ❌ | **Deliberately not built.** It covers income this app does not hold — employment, property, dividends. The user finishes the year in HMRC's own service. |

---

## What stands between this and "everything connected"

| # | Item | Who can do it |
|---|---|---|
| 1 | `ANTHROPIC_API_KEY` — turns on receipt scanning | You, at console.anthropic.com |
| 2 | `COMPANIES_HOUSE_API_KEY` — turns on company lookup | You, free, at developer.company-information.service.gov.uk (a personal account, no UK company needed) |
| 3 | Walk the HMRC flow with the sandbox test user | You on a phone, or me if you paste the outcome |
| 4 | HMRC production credentials | HMRC, weeks of review |
| 5 | Test on a physical Android device | You, from the APK |

Nothing else in the app is a mockup: every control has a real handler,
every route is registered and reachable, and there is no invented data
anywhere in the codebase.
