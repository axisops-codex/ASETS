# Google Play — Data safety form (answers)

Play Console → *App content* → *Data safety*. Answer exactly as below; the app
contains no analytics or advertising SDK, so most of the form is "No".

## Overview questions

| Question | Answer |
|---|---|
| Does your app collect or share any of the required user data types? | **Yes** |
| Is all of the user data collected by your app encrypted in transit? | **Yes** (HTTPS only) |
| Do you provide a way for users to request that their data is deleted? | **Yes** — URL: `https://<your-api-host>/legal/delete-account` |

## Data types — declare these

| Category | Data type | Collected | Shared | Processed ephemerally | Required | Purpose |
|---|---|---|---|---|---|---|
| Personal info | Name | Yes | No | No | Required | App functionality |
| Personal info | Email address | Yes | No | No | Required | App functionality, Account management |
| Personal info | Address | Yes | No | No | Optional | App functionality (invoice header) |
| Personal info | Other info (UTR, NI number, company/VAT number, client contact details) | Yes | No | No | Optional | App functionality |
| Financial info | Other financial info (invoices, expenses, income totals, bank details shown on invoices) | Yes | No | No | Required | App functionality |
| Photos and videos | Photos | Yes | No | No | Optional | App functionality (receipt proof + text extraction) |
| Personal info | Other info (National Insurance number) | Yes | **Yes — to HMRC** | No | Optional | App functionality (only if the user connects to HMRC) |
| Financial info | Other financial info (income and expense totals submitted to HMRC) | Yes | **Yes — to HMRC** | No | Optional | App functionality |
| Device or other IDs | Device or other IDs | Yes | **Yes — to HMRC** | No | Optional | Fraud prevention (a legal requirement of Making Tax Digital) |
| App activity | — | No | No | — | — | — |
| App info and performance | Crash logs / diagnostics | No | No | — | — | — |
| Location | — | No | No | — | — | — |

**Security practices**
- Data is encrypted in transit: **Yes**
- Users can request data deletion: **Yes** (in-app and via the URL above)
- Committed to Play Families Policy: **No** (not a children's app)
- Independent security review: **No**

**Note on "Shared".** Passing data to your own processors (hosting, receipt
OCR, email delivery, Companies House lookup) is *not* "sharing" under Play's
definition — it is service provision, so answer **No** for those.

**HMRC is different.** HMRC is a separate data controller, not our processor,
so the three rows marked above **must** be declared as shared — but only if you
ship with HMRC filing enabled. If v1 ships with `HMRC_CLIENT_ID` unset (the
feature then reports `configured: false` and the app hides it), remove those
three rows and the device-ID declaration.

**On the device identifier.** ASETS generates a random UUID per install purely
to satisfy HMRC's fraud prevention requirement. It is not an advertising ID, it
is not used for tracking or analytics, and it is never shared with anyone but
HMRC. Say exactly that if Play queries it.

---

# Other Play Console content sections

**App access** — "All functionality is available without special access"? **No.**
Provide the reviewer credentials from `store/review-notes.md`.

**Ads** — "Does your app contain ads?" **No.**

**Content rating questionnaire** — category *Utility, Productivity, Communication
or Other*; answer **No** to every violence/sexual/drugs/gambling question. The
app has no user-to-user communication and no user-generated content sharing.
Expected outcome: PEGI 3 / ESRB Everyone.

**Target audience and content** — target age group **18 and over**. Not appealing
to children.

**News app** — No. **COVID-19 app** — No. **Data safety: financial features** —
if asked whether the app is a *financial services* app: it is a bookkeeping and
tax-estimate tool, **not** a lending, banking, payments, crypto or investment app,
so the financial-services declaration does **not** apply. It does not process
payments, hold funds, or connect to a bank account.

**Government apps** — No. The app is not affiliated with or endorsed by HMRC.
It *connects to* HMRC's public Making Tax Digital API with the user's own
consent, which is not the same thing. No screenshot or listing text may imply
endorsement, and the HMRC logo or crest must never appear.

**Financial features declaration** — if Play asks, ASETS is a bookkeeping and
tax-submission tool. It does not lend, hold funds, process payments, deal in
crypto, or connect to a bank account.
