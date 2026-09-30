#!/usr/bin/env bash
# Cloud Run 배포: API(공개) + Worker(비공개, Cloud Tasks가 호출) + Cloud Tasks + Cloud Scheduler + GCS
# DB는 Neon(외부)을 사용한다. 재실행해도 안전하도록(idempotent) 작성했다.
#
# 사용법:
#   export PROJECT_ID=... DATABASE_URL='postgresql://...neon.tech/...?sslmode=require' WEB_ORIGINS=https://<web>.vercel.app
#   ./infra/gcp/deploy.sh
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID 필요}" "${DATABASE_URL:?Neon DATABASE_URL 필요}" "${WEB_ORIGINS:?Vercel 웹 주소 필요}"
REGION="${REGION:-asia-northeast3}"          # 서울
BUCKET="${BUCKET:-${PROJECT_ID}-media-preflight}"
REPO="media-preflight"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/api:$(git rev-parse --short HEAD)"
RUN_SA="preflight-run@${PROJECT_ID}.iam.gserviceaccount.com"       # API/worker 실행 계정
TASKS_SA="preflight-tasks@${PROJECT_ID}.iam.gserviceaccount.com"   # worker 호출(OIDC) 계정
cd "$(dirname "$0")/../.."
gcloud config set project "$PROJECT_ID" >/dev/null

echo "▶ APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  cloudtasks.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com storage.googleapis.com

echo "▶ Service accounts"
for sa in preflight-run preflight-tasks; do
  gcloud iam service-accounts describe "${sa}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$sa"
done
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${RUN_SA}" --role roles/cloudtasks.enqueuer --condition=None >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$TASKS_SA" --member "serviceAccount:${RUN_SA}" --role roles/iam.serviceAccountUser >/dev/null

echo "▶ Storage (GCS, S3 호환 HMAC)"
gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 ||
  gcloud storage buckets create "gs://${BUCKET}" --location "$REGION" --uniform-bucket-level-access
python3 - "$WEB_ORIGINS" > /tmp/preflight-cors.json <<'PY'
import json, sys
print(json.dumps([{"origin": sys.argv[1].split(","), "method": ["PUT", "GET", "HEAD"], "responseHeader": ["Content-Type", "ETag"], "maxAgeSeconds": 3600}]))
PY
echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":1}}]}' > /tmp/preflight-lifecycle.json
gcloud storage buckets update "gs://${BUCKET}" --cors-file /tmp/preflight-cors.json --lifecycle-file /tmp/preflight-lifecycle.json
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member "serviceAccount:${RUN_SA}" --role roles/storage.objectAdmin >/dev/null

secret() {  # name value
  gcloud secrets describe "$1" >/dev/null 2>&1 || gcloud secrets create "$1" --replication-policy automatic >/dev/null
  printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=- >/dev/null
  gcloud secrets add-iam-policy-binding "$1" --member "serviceAccount:${RUN_SA}" --role roles/secretmanager.secretAccessor >/dev/null
}
if ! gcloud secrets describe preflight-s3-secret >/dev/null 2>&1; then
  read -r ACCESS SECRET < <(gcloud storage hmac create "$RUN_SA" --format="value(metadata.accessId,secret)")
  secret preflight-s3-access "$ACCESS"
  secret preflight-s3-secret "$SECRET"
fi
secret preflight-database-url "$DATABASE_URL"

echo "▶ Image"
gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION"
gcloud builds submit apps/api --tag "$IMAGE"

echo "▶ Cloud Tasks queue"
gcloud tasks queues describe media --location "$REGION" >/dev/null 2>&1 ||
  gcloud tasks queues create media --location "$REGION" --max-attempts 2 --max-concurrent-dispatches 10

COMMON_ENV="OBJECT_STORAGE_ENDPOINT=https://storage.googleapis.com,OBJECT_STORAGE_BUCKET=${BUCKET},OBJECT_STORAGE_REGION=auto,QUEUE_BACKEND=cloudtasks,GCP_PROJECT=${PROJECT_ID},GCP_LOCATION=${REGION},TASKS_QUEUE=media,TASKS_SERVICE_ACCOUNT=${TASKS_SA},FILE_RETENTION_HOURS=24,SIGNED_URL_TTL_SECONDS=600,JOB_TIMEOUT_SECONDS=1800"
SECRETS="DATABASE_URL=preflight-database-url:latest,OBJECT_STORAGE_ACCESS_KEY=preflight-s3-access:latest,OBJECT_STORAGE_SECRET_KEY=preflight-s3-secret:latest"

echo "▶ Worker (비공개, 인스턴스당 작업 1개)"
gcloud run deploy preflight-worker --image "$IMAGE" --region "$REGION" --service-account "$RUN_SA" \
  --no-allow-unauthenticated --command uvicorn --args "preflight.worker:app,--host,0.0.0.0,--port,8080" \
  --cpu 2 --memory 2Gi --concurrency 1 --timeout 1800 --max-instances 3 \
  --set-env-vars "$COMMON_ENV" --set-secrets "$SECRETS"
WORKER_URL=$(gcloud run services describe preflight-worker --region "$REGION" --format 'value(status.url)')
gcloud run services add-iam-policy-binding preflight-worker --region "$REGION" \
  --member "serviceAccount:${TASKS_SA}" --role roles/run.invoker >/dev/null

echo "▶ API (공개)"
gcloud run deploy preflight-api --image "$IMAGE" --region "$REGION" --service-account "$RUN_SA" \
  --allow-unauthenticated --cpu 1 --memory 512Mi --max-instances 3 \
  --set-env-vars "^;^${COMMON_ENV//,/;};WORKER_URL=${WORKER_URL};WEB_ORIGINS=${WEB_ORIGINS}" --set-secrets "$SECRETS"
API_URL=$(gcloud run services describe preflight-api --region "$REGION" --format 'value(status.url)')

echo "▶ Cleanup scheduler (1시간마다, lifecycle rule과 별개로 DB 상태를 EXPIRED로 갱신)"
gcloud scheduler jobs describe preflight-cleanup --location "$REGION" >/dev/null 2>&1 ||
  gcloud scheduler jobs create http preflight-cleanup --location "$REGION" --schedule "0 * * * *" \
    --uri "${WORKER_URL}/tasks/cleanup" --http-method POST --headers Content-Type=application/json --message-body '{}' \
    --oidc-service-account-email "$TASKS_SA" --oidc-token-audience "$WORKER_URL"

echo
echo "✔ API:    ${API_URL}  (health: ${API_URL}/api/v1/health)"
echo "✔ Worker: ${WORKER_URL}"
echo "→ Vercel 환경변수 NEXT_PUBLIC_API_URL=${API_URL}"
