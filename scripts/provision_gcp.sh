#!/usr/bin/env bash
# One-time Google Cloud setup for the ASETS API.
#
#   ./scripts/provision_gcp.sh
#   PROJECT_ID=my-project ./scripts/provision_gcp.sh
#   DRY_RUN=1 ./scripts/provision_gcp.sh
#
# Creates only what Cloud Run needs: an Artifact Registry repository, a
# runtime service account, and the secrets. The database is Supabase, so
# there is no Cloud SQL instance and no storage bucket to pay for.
#
# Cost at one user: nothing. Cloud Run's free tier covers 2M requests a
# month and the service scales to zero between them.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-europe-west2}"          # London
REPO="${REPO:-asets}"
RUNTIME_SA="${RUNTIME_SA:-asets-api}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/backend/.env"

[ -n "$PROJECT_ID" ] || { echo "Set PROJECT_ID or run: gcloud config set project <id>" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE not found — run scripts/gen_secrets.py first" >&2; exit 1; }

run() { if [ "${DRY_RUN:-0}" = "1" ]; then printf '  $ %s\n' "$*"; else "$@"; fi; }
step() { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }
exists() { "$@" >/dev/null 2>&1; }

step "Project $PROJECT_ID / region $REGION"

step "Enabling APIs"
run gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com --project="$PROJECT_ID"

step "Artifact Registry"
if exists gcloud artifacts repositories describe "$REPO" --location="$REGION" --project="$PROJECT_ID"; then
  echo "  · repository $REPO exists"
else
  run gcloud artifacts repositories create "$REPO" --repository-format=docker \
    --location="$REGION" --description="ASETS container images" --project="$PROJECT_ID"
fi

step "Runtime service account"
SA_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
if exists gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID"; then
  echo "  · $SA_EMAIL exists"
else
  run gcloud iam service-accounts create "$RUNTIME_SA" \
    --display-name="ASETS API runtime" --project="$PROJECT_ID"
fi
# IAM is eventually consistent: a service account created a second ago
# is not always visible to the policy API yet.
grant_role() {
  local role="$1" attempt
  for attempt in 1 2 3 4 5 6; do
    if run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
         --member="serviceAccount:$SA_EMAIL" --role="$role" \
         --condition=None --quiet >/dev/null 2>&1; then
      echo "  ✓ $role"
      return 0
    fi
    sleep 5
  done
  echo "  ✗ could not grant $role — re-run this script in a minute" >&2
  return 1
}
grant_role roles/secretmanager.secretAccessor

step "Cloud Build permissions"
# Cloud Build runs as the Compute Engine default service account on
# projects created after mid-2024, and it needs write access to push the
# image into the repository we just created.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/artifactregistry.writer roles/logging.logWriter; do
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$BUILD_SA" --role="$role" --condition=None --quiet >/dev/null \
    && echo "  ✓ $role -> $BUILD_SA"
done

# Cloud Run needs to be allowed to act as the runtime service account.
run gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" --project="$PROJECT_ID" --quiet >/dev/null 2>&1 || true

step "Secrets"
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

put_secret() {
  local name="$1" value="$2"
  [ -n "$value" ] || { echo "  · $name — empty, skipped"; return; }
  if ! exists gcloud secrets describe "$name" --project="$PROJECT_ID"; then
    run gcloud secrets create "$name" --replication-policy=automatic --project="$PROJECT_ID"
  fi
  if [ "${DRY_RUN:-0}" = "1" ]; then
    printf '  $ gcloud secrets versions add %s --data-file=-\n' "$name"
  else
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- \
      --project="$PROJECT_ID" >/dev/null
    echo "  ✓ $name"
  fi
}

put_secret DATABASE_URL "${DATABASE_URL:-}"
put_secret MIGRATION_DATABASE_URL "${MIGRATION_DATABASE_URL:-}"
put_secret DB_APP_PASSWORD "${DB_APP_PASSWORD:-}"
put_secret JWT_SECRET "${JWT_SECRET:-}"
put_secret TOKEN_ENCRYPTION_KEY "${TOKEN_ENCRYPTION_KEY:-}"
put_secret ANTHROPIC_API_KEY "${ANTHROPIC_API_KEY:-}"
put_secret HMRC_CLIENT_ID "${HMRC_CLIENT_ID:-}"
put_secret HMRC_CLIENT_SECRET "${HMRC_CLIENT_SECRET:-}"
put_secret COMPANIES_HOUSE_API_KEY "${COMPANIES_HOUSE_API_KEY:-}"

mkdir -p "$ROOT/deploy"
cat > "$ROOT/deploy/gcp.env" <<EOF
# Written by scripts/provision_gcp.sh — read by scripts/deploy_cloudrun.sh
PROJECT_ID=$PROJECT_ID
REGION=$REGION
REPO=$REPO
RUNTIME_SA=$SA_EMAIL
HMRC_ENVIRONMENT=${HMRC_ENVIRONMENT:-sandbox}
EOF

step "Done"
echo "Now run: ./scripts/deploy_cloudrun.sh"
