#!/usr/bin/env bash
# Build, migrate, deploy. Run it as often as you like.
#
#   ./scripts/deploy_cloudrun.sh
#   TAG=v1.0.1 ./scripts/deploy_cloudrun.sh
#   DRY_RUN=1 ./scripts/deploy_cloudrun.sh
#
# The migration job runs to completion against the new image before any
# traffic moves, so a failed migration leaves the previous revision
# serving.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_OUT="$ROOT/deploy/gcp.env"
[ -f "$ENV_OUT" ] || { echo "deploy/gcp.env missing — run ./scripts/provision_gcp.sh first" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; . "$ENV_OUT"; set +a

SERVICE="${SERVICE:-asets-api}"
JOB="${JOB:-asets-migrate}"
TAG="${TAG:-$(date +%Y%m%d-%H%M%S)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/asets-api:${TAG}"

run() { if [ "${DRY_RUN:-0}" = "1" ]; then printf '  $ %s\n' "$*"; else "$@"; fi; }
step() { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }
secret_exists() { gcloud secrets describe "$1" --project="$PROJECT_ID" >/dev/null 2>&1; }

# Only wire up secrets that exist, so an unconfigured optional
# integration cannot fail the deploy.
SECRETS="DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest"
for name in TOKEN_ENCRYPTION_KEY ANTHROPIC_API_KEY HMRC_CLIENT_ID HMRC_CLIENT_SECRET \
            COMPANIES_HOUSE_API_KEY; do
  secret_exists "$name" && SECRETS="${SECRETS},${name}=${name}:latest"
done

step "Building $IMAGE"
run gcloud builds submit "$ROOT/backend" --tag "$IMAGE" --project="$PROJECT_ID"

step "Migrating the database"
JOB_ARGS=(
  --image="$IMAGE" --region="$REGION" --project="$PROJECT_ID"
  --service-account="$RUNTIME_SA"
  --set-secrets="MIGRATION_DATABASE_URL=MIGRATION_DATABASE_URL:latest,DB_APP_PASSWORD=DB_APP_PASSWORD:latest"
  --command=python --args=-m,db.deploy
  --max-retries=0 --task-timeout=10m
)
if gcloud run jobs describe "$JOB" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  run gcloud run jobs update "$JOB" "${JOB_ARGS[@]}"
else
  run gcloud run jobs create "$JOB" "${JOB_ARGS[@]}"
fi
run gcloud run jobs execute "$JOB" --region="$REGION" --project="$PROJECT_ID" --wait

step "Deploying $SERVICE"
run gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="$RUNTIME_SA" \
  --allow-unauthenticated \
  --set-secrets="$SECRETS" \
  --set-env-vars="STORAGE_BACKEND=postgres,LLM_PROVIDER=anthropic,CORS_ORIGINS=*,HMRC_ENVIRONMENT=${HMRC_ENVIRONMENT:-sandbox},HMRC_APP_RETURN_URL=asets://hmrc,HMRC_PRODUCT_NAME=ASETS,HMRC_SERVER_VERSION=${TAG},DB_POOL_MAX=5" \
  --cpu=1 --memory=512Mi --concurrency=40 --timeout=60 \
  --min-instances=0 --max-instances=3

if [ "${DRY_RUN:-0}" = "1" ]; then printf '\n(dry run — nothing changed)\n'; exit 0; fi

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT_ID" \
        --format='value(status.url)')"

step "Pointing HMRC's redirect at this service"
gcloud run services update "$SERVICE" --region="$REGION" --project="$PROJECT_ID" \
  --update-env-vars="HMRC_REDIRECT_URI=${URL}/api/hmrc/callback" >/dev/null

step "Checking it is alive"
sleep 5
curl -fsS "$URL/api/health" | python3 -m json.tool || {
  echo "Health check failed. Logs:"
  gcloud run services logs read "$SERVICE" --region="$REGION" --project="$PROJECT_ID" --limit=50
  exit 1
}

cat <<EOF

Deployed: $URL

  Health          $URL/api/health
  Privacy policy  $URL/legal/privacy
  HMRC redirect   $URL/api/hmrc/callback   <- register this on the HMRC Developer Hub

Next:
  · Put $URL into frontend/eas.json (preview + production).
  · Build the client's APK:  cd frontend && eas build --profile preview --platform android
EOF
