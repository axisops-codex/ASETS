# HMRC Making Tax Digital for Income Tax

ASETS submits quarterly updates for self-employment income to HMRC's MTD
ITSA APIs. This is what is implemented, what it needs from you, and what
is deliberately not implemented.

## What is implemented

| Capability | HMRC API | Version | Endpoint in ASETS |
|---|---|---|---|
| Connect a user's HMRC account | OAuth 2.0 | — | `POST /api/hmrc/connect`, `GET /api/hmrc/callback` |
| Find the user's self-employment business | Business Details | 2.0 | `GET /api/hmrc/businesses` |
| Read quarterly obligations and deadlines | Obligations | 3.0 | `GET /api/hmrc/obligations` |
| Preview what would be declared | — | — | `GET /api/hmrc/quarter-preview` |
| Send a quarterly (cumulative) update | Self Employment Business | 5.0 | `POST /api/hmrc/submit-quarter` |
| Trigger and read HMRC's own calculation | Individual Calculations | 8.0 | `POST /api/hmrc/calculation`, `GET /api/hmrc/calculation/{id}` |
| Show everything ASETS has ever sent | — | — | `GET /api/hmrc/submissions` |

Quarterly updates use the **cumulative** endpoint
(`PUT …/cumulative/{taxYear}`), which is the shape for tax year 2025-26
onward: each update reports 6 April to the end of the quarter, so a later
update supersedes an earlier one.

## What is not implemented, on purpose

**Final declaration (crystallisation).** That is the legal statement that
a whole year's figures are complete and correct, and it covers income
ASETS does not hold — employment, property, dividends, interest. Sending
it from an app that only knows about self-employment would be wrong.
Users finish the year in HMRC's own service or with their accountant.

**UK property and foreign property income.** ASETS models one
self-employment business.

**Amending a previously submitted period through the pre-2025-26
`period` endpoint.** The path is in
[`hmrc/client.py`](../backend/hmrc/client.py) but no route uses it.

## Checking the setup

```bash
python3 scripts/check_hmrc.py
```

Read-only, no browser and no test user needed. It answers the four
things that actually block a submission: whether the credentials are
valid and for which environment, whether the application is subscribed to
every API ASETS calls (at the versions it pins), and whether the redirect
URI is registered. Run it after any change on the Developer Hub.

## Getting credentials

1. Register at [developer.service.hmrc.gov.uk](https://developer.service.hmrc.gov.uk/).
2. Create an application. Sandbox credentials are issued immediately.
3. Subscribe the application to: **Business Details**, **Obligations**,
   **Self Employment Business**, **Individual Calculations**, and
   **Create Test User** (sandbox only).
4. Add the redirect URI — exactly, including scheme and path:
   `https://<your-cloud-run-url>/api/hmrc/callback`
   HMRC matches it character for character; a missing `/api` or a trailing
   slash produces `redirect_uri is invalid` at the sign-in step, with no
   hint as to which part is wrong.
5. Put the client ID and secret into `backend/.env`, or Secret Manager in
   production:

```bash
gcloud secrets versions add HMRC_CLIENT_ID     --data-file=- <<< 'your-client-id'
gcloud secrets versions add HMRC_CLIENT_SECRET --data-file=- <<< 'your-client-secret'
./scripts/deploy_cloudrun.sh
```

## What the Developer Hub asks for

Under **Customer usage information** on the application page:

| Field | Value |
|---|---|
| Privacy policy URL | `https://<your-cloud-run-url>/legal/privacy` |
| Terms and conditions URL | `https://<your-cloud-run-url>/legal/terms` |

Both are served by the API itself, so they cannot drift out of step with
the deployment, and the privacy policy already covers what HMRC's review
looks for: the National Insurance number, the stored tokens, and the
fraud prevention data that the law requires us to send.

**Application grant length — 18 months.** That is how long a user's
authorisation lasts before they must reconnect; a user can also revoke it
at any time from their own tax account. Both cases surface the same way:
the refresh token stops working. ASETS treats that as *not connected*
(HTTP 409, "Reconnect in Settings → HMRC") rather than a server error,
records the reason on the connection, and shows it on the HMRC screen.
A genuine HMRC outage is deliberately *not* mistaken for this — it stays
a 502 telling the user to try again, so nobody is sent off to reconnect
an account that is perfectly healthy.

## Testing against the sandbox

Create a sandbox test user (an individual with MTD ITSA enrolment) with
HMRC's Create Test User API, then sign in with those credentials during
the OAuth step. The test user comes with its own NI number — use that in
the app, not a real one.

```bash
curl -X POST 'https://test-api.service.hmrc.gov.uk/create-test-user/individuals' \
  -H 'Accept: application/vnd.hmrc.1.0+json' \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $SERVER_TOKEN" \
  -d '{"serviceNames":["mtd-income-tax"]}'
```

HMRC's sandbox returns canned data, and several endpoints let you choose
which scenario with a `Gov-Test-Scenario` header. ASETS does not send
that header; add it in `hmrc/client.call()` if you want to exercise a
specific rejection.

## Fraud prevention headers

HMRC requires headers describing the device that originated a
submission. Getting them wrong is the single most common reason for
rejection, and HMRC monitors compliance separately from whether calls
succeed.

ASETS is **`MOBILE_APP_VIA_SERVER`**: the phone collects what only the
phone knows, and the API adds the rest.

| Source | Headers |
|---|---|
| The phone, in one base64url JSON blob in `X-ASETS-Device` (see [`frontend/src/utils/device.ts`](../frontend/src/utils/device.ts)) | `Gov-Client-Device-ID`, `Gov-Client-Timezone`, `Gov-Client-Local-IPs`, `Gov-Client-Local-IPs-Timestamp`, `Gov-Client-Screens`, `Gov-Client-Window-Size`, `Gov-Client-User-Agent`, and the app half of `Gov-Vendor-Version` |
| The API ([`backend/hmrc/fraud.py`](../backend/hmrc/fraud.py)) | `Gov-Client-Connection-Method`, `Gov-Client-Public-IP`, `Gov-Client-Public-IP-Timestamp`, `Gov-Client-Public-Port`, `Gov-Client-User-IDs`, `Gov-Vendor-Product-Name`, `Gov-Vendor-Public-IP`, `Gov-Vendor-Forwarded` |

Two rules the code follows deliberately:

- **Nothing is invented.** A value that cannot be measured is omitted.
  `GET /api/hmrc/status` returns `missing_fraud_headers`, and the app
  shows it, so a device problem surfaces before a submission is rejected.
- **`Gov-Client-MAC-Addresses` is not sent.** HMRC does not require it
  for this connection method, and mobile operating systems no longer
  expose real MAC addresses.

**`Gov-Vendor-Public-IP` and `Gov-Vendor-Forwarded`.** HMRC wants the
server's own public address, and both halves of `Gov-Vendor-Forwarded`
(`by=` and `for=`) must be *IP addresses* — putting a hostname in `by`,
which is what the `Host` header gives you, is rejected outright.

Cloud Run has no fixed egress IP, so instead of paying for a static one
the API asks what its address is at startup (`checkip.amazonaws.com`,
falling back to `api.ipify.org`), caches it for the life of the instance
and uses it for both headers. It is the real address, which is what HMRC
is asking for. Setting `HMRC_VENDOR_PUBLIC_IP` overrides the lookup — do
that if you later put the service behind Cloud NAT with a reserved
address.

**`Gov-Client-Multi-Factor`** is sent only when the user has the
biometric app lock switched on. Declaring a factor that was not used
would be worse than omitting the header.

**`Gov-Vendor-License-IDs` is deliberately absent.** ASETS is not
licensed software — there are no licence keys on the device to hash.
HMRC's validator flags this as a warning whose own text says *"you must
contact us explaining why you cannot submit this header"*, so the
explanation goes in the production application rather than a fabricated
value:

> ASETS is not licensed software. There is no licence key issued to the
> user or stored on the device, so there is nothing to hash into
> Gov-Vendor-License-IDs. Installations are identified to HMRC through
> Gov-Client-Device-ID and Gov-Client-User-IDs, both of which we do send.

**Check the whole set before applying for production:**

```bash
python3 scripts/check_hmrc.py
```

That runs the real headers through HMRC's **Test Fraud Prevention
Headers** API. The target is zero errors; the licence-IDs warning above
is expected and is reported as such.

## Going to production

Sandbox access is instant; production is not. HMRC reviews the
application before issuing production credentials, and expects:

- a demonstration of the end-to-end journey,
- fraud prevention headers that pass their validator,
- the software listed on HMRC's "find software" page,
- terms and a privacy notice covering the tax data (both are in
  `backend/legal/`, already updated for this).

Budget several weeks. When the credentials arrive:

```bash
gcloud secrets versions add HMRC_CLIENT_ID     --data-file=- <<< 'prod-id'
gcloud secrets versions add HMRC_CLIENT_SECRET --data-file=- <<< 'prod-secret'
gcloud run services update asets-api --region=europe-west2 \
  --update-env-vars=HMRC_ENVIRONMENT=production
```

Nothing else changes — the base URL follows `HMRC_ENVIRONMENT`.

## How data maps onto HMRC's fields

Turnover is invoiced income in the period (the accruals basis the rest of
the app reports on), so the figure on the dashboard is the figure that
reaches HMRC. Expense categories map to HMRC's expense boxes through
`asets.expense_categories.hmrc_field`:

| ASETS category | HMRC field |
|---|---|
| Software, Equipment, Phone / Internet | `adminCosts` |
| Supervision, Professional fees | `professionalFees` |
| Insurance, Office / Rent | `premisesRunningCosts` |
| Travel | `carVanTravelExpenses` |
| Training / CPD, Other | `otherExpenses` |

Changing a mapping is a migration, not a code edit — the lookup table is
read-only to the application.

## Tokens

Access and refresh tokens, and the NI number, are encrypted with Fernet
(`TOKEN_ENCRYPTION_KEY`) before they are written, so a database dump
discloses neither. **Rotating that key makes existing connections
undecryptable and every user has to reconnect** — it is not a routine
rotation.

HMRC issues a fresh refresh token on every refresh and invalidates the
old one, so the new pair is written in its own transaction: if a later
step fails and rolls back, the connection would otherwise be stranded
permanently. There is a test for that.
