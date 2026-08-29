# Submission checklist

Tick straight down. Anything unticked is a rejection waiting to happen.

## Infrastructure
- [ ] `scripts/gen_secrets.py` run; `backend/.env` exists and is git-ignored
- [ ] `./scripts/provision_gcp.sh` completed; `deploy/gcp.env` written
- [ ] `./scripts/deploy_cloudrun.sh` completed; migrations applied by the job
- [ ] `curl $API/api/health` returns `"status":"ok"`, `"database":"up"`
- [ ] Database backups understood (Supabase free tier keeps 7 days; take your own `pg_dump` for anything critical)
- [ ] `JWT_SECRET` and `TOKEN_ENCRYPTION_KEY` are the generated values, in Secret Manager
- [ ] `$API/legal/privacy`, `/terms`, `/delete-account`, `/support` all return 200
- [ ] Demo account seeded (`scripts/seed_demo.py`) and you can log into it from the app

## App config
- [ ] `ios.bundleIdentifier` / `android.package` are final (they can never change)
- [ ] `EXPO_PUBLIC_BACKEND_URL` in `eas.json` points at the **public** API for both
      `preview` and `production`
- [ ] `version` in `app.json` is the version you mean to ship
- [ ] `./scripts/preflight.sh` passes

## Tested on a real device (not a simulator)
- [ ] Register → sign out → sign in
- [ ] Client → invoice → share PDF
- [ ] Camera receipt scan reads amount and date
- [ ] Face ID / fingerprint lock engages on reopen
- [ ] Tax year estimate + CSV export
- [ ] Privacy / Terms / Help links open
- [ ] Delete account wipes the data
- [ ] Airplane mode shows a readable error, not a blank screen
- [ ] Settings → HMRC: connect against the sandbox, submit a quarter, see it listed

## HMRC (skip if shipping with the feature disabled)
- [ ] Application registered on the Developer Hub and subscribed to all four APIs
- [ ] Redirect URI registered exactly as the deployed one
- [ ] Sandbox test user created and the whole flow walked on a real device
- [ ] Static egress IP configured and `HMRC_VENDOR_PUBLIC_IP` set
- [ ] Fraud prevention headers pass HMRC's Test Fraud Prevention Headers API
- [ ] Production credentials applied for (weeks of lead time)
- [ ] Store answers updated for the HMRC data (see the notes in `play-data-safety.md`
      and `apple-privacy.md` — they differ depending on whether HMRC ships enabled)

## Legal
- [ ] Registered legal entity name and postal address added to
      `backend/legal/privacy.html` (search for `TODO`) and redeployed
- [ ] ICO registration considered (most UK data controllers need one)
- [ ] Nothing in the listing, screenshots or app implies HMRC affiliation
- [ ] "Estimate, not tax advice" wording present in the listing and in the app

## Google Play
- [ ] App created, English (UK), Free
- [ ] Play service-account JSON at `frontend/credentials/play-service-account.json`
- [ ] Store listing text + graphics uploaded (`store/listing.md`, `store/screenshots.md`)
- [ ] Data safety form completed (`store/play-data-safety.md`)
- [ ] Content rating questionnaire completed
- [ ] Target audience: 18+
- [ ] App access: demo credentials supplied (`store/review-notes.md`)
- [ ] Privacy policy URL + account deletion URL entered
- [ ] AAB uploaded to internal testing and installed successfully
- [ ] Closed test with 12 testers running (personal accounts: 14 days before production)

## Apple App Store
- [ ] App record created with the matching bundle ID
- [ ] `submit.production.ios` in `eas.json` filled in (Apple ID, ASC app ID, Team ID)
- [ ] Build uploaded and processed; TestFlight install verified
- [ ] Listing text, keywords, promotional text entered (`store/listing.md`)
- [ ] 6.9" iPhone screenshots uploaded — **and 13" iPad**, because
      `supportsTablet: true` (or set it to `false` and rebuild)
- [ ] App Privacy answers completed (`store/apple-privacy.md`)
- [ ] Export compliance: exempt (already declared in `app.json`)
- [ ] Age rating 4+
- [ ] Review notes with demo credentials and the deletion path (`store/review-notes.md`)
- [ ] Availability restricted to the United Kingdom

## Expected Android permissions (so the manifest holds no surprises)
`CAMERA` (receipt photos) · `USE_BIOMETRIC` / `USE_FINGERPRINT` (app lock) ·
`INTERNET`, `VIBRATE`, `READ/WRITE_EXTERNAL_STORAGE`, `SYSTEM_ALERT_WINDOW`
(React Native / Expo defaults). `RECORD_AUDIO` and `READ_MEDIA_VIDEO` are
explicitly stripped by `blockedPermissions` in `app.json`.

## After launch
- [ ] Set up uptime monitoring on `$API/api/health`
- [ ] Watch the first reviews for tax-figure complaints — the rates are hardcoded
      for 2024/25 and will need a yearly update
- [ ] Diary the Apple membership renewal (annual)
