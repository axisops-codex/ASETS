# Getting ASETS to your client

The whole thing runs on free tiers: Supabase for the database, Cloud Run
for the API, an Android APK sent straight to the phone. **Nothing here
costs you or the client anything.**

---

## 1. Secrets

```bash
python3 scripts/gen_secrets.py
```

Writes `backend/.env` (mode 600, git-ignored). Two of the generated
values cannot be rotated casually:

- `JWT_SECRET` — rotating signs everyone out.
- `TOKEN_ENCRYPTION_KEY` — rotating makes stored HMRC connections
  undecryptable; the user has to reconnect.

Then paste in your HMRC client ID and secret, and the two optional keys:
`ANTHROPIC_API_KEY` for receipt scanning and `COMPANIES_HOUSE_API_KEY`
for company lookup. Either left blank disables that feature cleanly — the
app says so rather than erroring.

## 2. Database — Supabase (free)

Currently the `asets` schema inside the **axis-builder** project
(`aesdrxhezmksxntsnvam`, eu-west-1) — Supabase's free tier allows two
projects per organisation and both were taken. It is namespaced and has
its own `asets_app` role, so it cannot see anything else in that
database, but it does share that project's 500 MB and its backups.

### Moving it to a project of its own

One command does the whole switchover:

```bash
python3 scripts/switch_database.py --supabase-ref <new-project-ref>
```

It asks for the new project's database password (Supabase dashboard →
Project Settings → Database), then finds the right pooler host, creates
the `asets_app` role, applies every migration, proves the app role can
connect and that row-level security denies by default, rewrites
`backend/.env`, updates the GCP secrets and redeploys. `--no-gcp` and
`--no-deploy` stop it earlier if you want to check something first.

Supabase runs more than one pooler fleet — newer projects are on
`aws-1-<region>.pooler.supabase.com`, older ones on `aws-0-…` — so the
script probes rather than guessing. Always the **session pooler** on port
5432, never `db.<ref>.supabase.co`, which is IPv6-only on the free tier
and unreachable from Cloud Run.

Carrying existing data across is deliberate and separate:

```bash
pg_dump "$OLD_MIGRATION_URL" --schema=asets --data-only --no-owner -Fc -f asets-data.dump
pg_restore --data-only --no-owner -d "$NEW_MIGRATION_URL" asets-data.dump
```

Afterwards, clear the old copy out — this touches nothing else in that
database:

```sql
DROP SCHEMA asets CASCADE;
DROP ROLE asets_app;
DROP ROLE asets_migrate;
```

## 3. API — Cloud Run (free)

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

./scripts/provision_gcp.sh      # Artifact Registry, service account, secrets
./scripts/deploy_cloudrun.sh    # build → migrate → deploy → health check
```

`min-instances=0`, so it costs nothing when nobody is using it and the
free tier (2M requests/month) covers a single client many times over.
The first request after an idle period takes a couple of seconds to wake.

Live now at **https://asets-api-7kd7b2l4kq-nw.a.run.app**. Verify:

```bash
API=$(gcloud run services describe asets-api --region=europe-west2 --format='value(status.url)')
curl -s $API/api/health | python3 -m json.tool
open $API/legal/privacy
```

## 4. HMRC

Credentials are configured and deployed (sandbox). Check the setup any
time with:

```bash
python3 scripts/check_hmrc.py
```

It verifies the credentials, every API subscription, and whether the
redirect URI is registered — read-only, no browser needed.

The redirect URI must be added to the application on the
[Developer Hub](https://developer.service.hmrc.gov.uk/), exactly:

```
https://asets-api-7kd7b2l4kq-nw.a.run.app/api/hmrc/callback
```

HMRC matches it character for character.

To change credentials later:

```bash
gcloud secrets versions add HMRC_CLIENT_ID     --data-file=- <<< 'your-id'
gcloud secrets versions add HMRC_CLIENT_SECRET --data-file=- <<< 'your-secret'
./scripts/deploy_cloudrun.sh
```

Details, including the fraud-prevention headers and what production
approval involves: [docs/HMRC.md](docs/HMRC.md).

## 5. The app on the client's phone

Already pointed at the API — `frontend/eas.json`, both profiles:

```json
"EXPO_PUBLIC_BACKEND_URL": "https://asets-api-7kd7b2l4kq-nw.a.run.app"
```

Then:

```bash
cd frontend
npx eas-cli login                                     # first time only
npx eas-cli init                                      # first time only
npx eas-cli build --profile preview --platform android
```

`npx eas-cli` avoids a global install — plain `eas` is not a command
unless you have run `npm install -g eas-cli`.

EAS emails you a download link. Send it to the client; they open it on
the phone and tap install (Android asks them to allow installs from that
browser once). No Play Console, no £20, no review.

Rebuild and resend the same way for every update.

### iPhone

There is no free route. Installing on someone else's iPhone needs the
Apple Developer Program (£99/year) — then TestFlight covers up to 100
testers without an App Store review. If the client is on iOS, that £99 is
unavoidable; everything in this repo is already set up for it.

## 6. Check before you hand it over

```bash
./scripts/preflight.sh
```

Bundle identifiers, assets, TypeScript, the backend test suite, the live
health endpoint and the four legal URLs.

On the phone itself:

- [ ] Register, sign out, sign back in
- [ ] Client → invoice → share the PDF
- [ ] Photograph a receipt; check the amount and date came out right
- [ ] Face ID / fingerprint lock: background the app, reopen
- [ ] Tax tab: pick a tax year, export the CSV
- [ ] Settings → HMRC: connect, submit a quarter, see it in the history
- [ ] Aeroplane mode shows a readable message, not a blank screen

## 7. Later: the app stores

If this grows beyond one client, everything for a store launch is already
written: listing copy, data-safety answers, privacy labels, review notes
and a screenshot spec, in [`store/`](store/). Start with
[`store/checklist.md`](store/checklist.md).

Two things to settle first: the bundle identifier
(`com.axisbsolutions.asets`) is permanent after the first upload, and the
privacy policy names *Axis B Solutions* as data controller — confirm the
registered name and add a postal address (search for `TODO` in
`backend/legal/privacy.html`).
