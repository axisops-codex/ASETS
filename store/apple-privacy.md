# App Store Connect — App Privacy ("nutrition label")

App Store Connect → your app → *App Privacy* → *Get started*.

## Data collected — declare these

For every type below: **Linked to the user: Yes**, **Used for tracking: No**,
purpose **App Functionality** only (never Analytics, never Advertising).

| Category | Data type |
|---|---|
| Contact Info | Name |
| Contact Info | Email Address |
| Contact Info | Physical Address |
| Financial Info | Other Financial Info (invoices, expenses, income, bank details for invoices) |
| User Content | Photos or Videos (receipt photographs) |
| User Content | Other User Content (client records, notes, business profile including UTR / NI / VAT numbers) |
| Identifiers | User ID (the account identifier) |
| Identifiers | Device ID — *only if shipping with HMRC filing enabled* |
| Sensitive Info | Other Sensitive Info (National Insurance number) — *only if shipping with HMRC filing enabled* |

## Not collected — leave unticked

Location · Contacts · Health & Fitness · Browsing History · Search History ·
Usage Data · Diagnostics · Advertising Data · Purchases · Audio Data.

If v1 ships with HMRC filing switched off (`HMRC_CLIENT_ID` unset — the app
then hides the feature), also leave **Device ID** and **Sensitive Info**
unticked and remove those two rows above.

**On the device identifier:** it is a random UUID generated per install, sent
only to HMRC because Making Tax Digital legally requires fraud prevention
headers. It is not the IDFA, it is not used for tracking, and App Tracking
Transparency does not apply.

**Tracking:** the app does **not** track. Do not implement App Tracking
Transparency — there is no `NSUserTrackingUsageDescription` and no ad SDK.

---

## Other App Store Connect fields

**Age rating** — 4+. Answer *None* to every content question. It is a business
tool; there is no in-app purchase, no user-generated content feed, no messaging.

**Export compliance** — the app uses only standard HTTPS/TLS. Answer:
*Does your app use encryption?* → **Yes** → *Only exempt encryption (HTTPS / platform
crypto)?* → **Yes**. `ITSAppUsesNonExemptEncryption: false` is already set in
`app.json`, so App Store Connect will not prompt on every build.

**Content rights** — you own or have licence to all content: Yes.

**Sign in with Apple** — **not required**: the app offers only its own
email/password login, no third-party social sign-in.

**Account deletion (Guideline 5.1.1(v))** — required and implemented:
*Settings → Delete account*. Also document it in the review notes so the
reviewer finds it.

**Category** — Primary: Finance. Secondary: Business.

**Availability** — United Kingdom only. The tax engine uses UK rates; shipping
worldwide invites rejections and bad reviews.
