# ASETS

*ADHD Self-Employed Taxes Support* — invoices, expenses and a live UK
Self Assessment estimate for self-employed practitioners, with quarterly
filing to HMRC.

```
frontend/   Expo / React Native app (iOS, Android, web)
backend/    FastAPI + PostgreSQL API, deployed to Cloud Run
  db/       schema, migrations, data access
  hmrc/     Making Tax Digital integration
  legal/    privacy policy, terms, support pages (served at /legal/*)
scripts/    secrets, provisioning, deploy, database switchover, preflight, demo seed
docs/       DATABASE.md, HMRC.md
store/      App Store / Play listing material, for when you go to the stores
```

## Try it now

Nothing to install — `npx` and the checked-in `node_modules` are enough,
and it talks to the live API:

```bash
cd /Users/marcogomes/AxisOS/ASETS/frontend
yarn install                       # first time only
npx expo start --web
```

Press `w` if it does not open by itself. Register an account and use it.

Three things a browser cannot do, so they need a real phone: the **camera
receipt scan**, the **Face ID / fingerprint lock**, and the **native share
sheet** (the invoice PDF downloads instead of opening a share menu).

## Put it on a phone

```bash
cd /Users/marcogomes/AxisOS/ASETS/frontend
npx eas-cli login                  # first time only
npx eas-cli build --profile preview --platform android
```

`npx eas-cli` runs without a global install — `eas` on its own is not a
command unless you have run `npm install -g eas-cli`. The build happens on
Expo's servers and finishes with a download link for the APK. Send that
link to the phone and tap install.

iPhone needs the Apple Developer Program (£99/year); there is no free
route onto someone else's iPhone.

## Work on the API

The API is deployed and the app points at it, so you only need this to
change the backend.

```bash
cd /Users/marcogomes/AxisOS/ASETS/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-prod.txt
uvicorn server:app --reload --port 8080          # uses backend/.env
```

*With Docker installed*, `docker compose up --build` from the repository
root runs the API against a local PostgreSQL instead of the live one.
Docker is not required for anything else.

## Test it

```bash
cd /Users/marcogomes/AxisOS/ASETS/backend && python -m pytest
npx tsc --noEmit
```

The backend suite creates its own throwaway PostgreSQL cluster, migrates
it and throws it away. It needs the PostgreSQL binaries on PATH
(`brew install postgresql@17`) and nothing else — no Docker, no server to
start.

## Ship it

[LAUNCH.md](LAUNCH.md) — deploy the API and get the app onto the phone.

## Design notes

- [docs/DATABASE.md](docs/DATABASE.md) — schema, row-level security, why
  money is `NUMERIC` and never a float.
- [docs/HMRC.md](docs/HMRC.md) — which HMRC APIs, fraud prevention
  headers, what is deliberately not implemented.
