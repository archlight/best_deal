#!/usr/bin/env bash
# Deploy Best Deal to Google Cloud Run, with the SQLite history replicated to Cloud Storage.
#
#   PROJECT=my-project ./deploy/cloudrun.sh
#   PROJECT=my-project BEST_DEAL_PASSWORD='choose-one' ./deploy/cloudrun.sh   # password-protect the app
#
# Safe to re-run: existing resources are reused and a new revision is deployed.
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-best-deal}"
BUCKET="${BUCKET:-${PROJECT}-best-deal-data}"
SA_NAME="${SERVICE}-run"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
SECRET="${SERVICE}-password"

[ -n "$PROJECT" ] || { echo "Set PROJECT or run: gcloud config set project <id>" >&2; exit 1; }
cd "$(dirname "$0")/.."
echo "Deploying $SERVICE to project $PROJECT in $REGION"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  storage.googleapis.com secretmanager.googleapis.com --project "$PROJECT"

if ! gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT" --location "$REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi

if ! gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" --display-name "Best Deal (Cloud Run)"
fi
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member "serviceAccount:$SA" --role roles/storage.objectAdmin >/dev/null

SECRET_FLAGS=()
if [ -n "${BEST_DEAL_PASSWORD:-}" ]; then
  if gcloud secrets describe "$SECRET" --project "$PROJECT" >/dev/null 2>&1; then
    printf %s "$BEST_DEAL_PASSWORD" | gcloud secrets versions add "$SECRET" --project "$PROJECT" --data-file=-
  else
    printf %s "$BEST_DEAL_PASSWORD" | gcloud secrets create "$SECRET" --project "$PROJECT" --data-file=-
  fi
  gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT" \
    --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null
  SECRET_FLAGS=(--set-secrets "BEST_DEAL_PASSWORD=${SECRET}:latest")
elif gcloud secrets describe "$SECRET" --project "$PROJECT" >/dev/null 2>&1; then
  SECRET_FLAGS=(--set-secrets "BEST_DEAL_PASSWORD=${SECRET}:latest")  # keep the existing password
else
  echo "WARNING: no BEST_DEAL_PASSWORD set; the app will be open to anyone with the URL." >&2
fi

# max-instances=1: SQLite + Litestream needs a single writer.
gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --source . \
  --service-account "$SA" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 40 \
  --cpu 1 \
  --memory 512Mi \
  --set-env-vars "LITESTREAM_REPLICA_URL=gcs://${BUCKET}/best_deal.db,BEST_DEAL_TZ=Asia/Singapore" \
  "${SECRET_FLAGS[@]}"

echo
echo "Deployed: $(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')"
