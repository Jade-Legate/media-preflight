import os

env = os.environ.get

DATABASE_URL = env("DATABASE_URL", "postgresql+psycopg://preflight:preflight@localhost:5432/preflight")
# managed Postgres는 postgres:// 또는 postgresql:// 형태로 준다 → psycopg3 driver로 맞춘다.
for _p in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_p):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_p):]
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

S3_ENDPOINT = env("OBJECT_STORAGE_ENDPOINT", "http://localhost:9000")
# 브라우저가 presigned URL로 직접 접근하는 주소. 로컬 compose에서는 컨테이너 내부 주소와 다르다.
S3_PUBLIC_ENDPOINT = env("OBJECT_STORAGE_PUBLIC_ENDPOINT", S3_ENDPOINT)
S3_BUCKET = env("OBJECT_STORAGE_BUCKET", "media-preflight")
S3_ACCESS_KEY = env("OBJECT_STORAGE_ACCESS_KEY", "preflight")
S3_SECRET_KEY = env("OBJECT_STORAGE_SECRET_KEY", "preflight-secret")
S3_REGION = env("OBJECT_STORAGE_REGION", "auto")
S3_CREATE_BUCKET = env("OBJECT_STORAGE_CREATE_BUCKET", "false") == "true"

MAX_UPLOAD_BYTES = int(env("MAX_UPLOAD_BYTES", str(2 * 1024**3)))
FILE_RETENTION_HOURS = int(env("FILE_RETENTION_HOURS", "24"))
SIGNED_URL_TTL_SECONDS = int(env("SIGNED_URL_TTL_SECONDS", "600"))
WEB_ORIGINS = [o.strip() for o in env("WEB_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
JOB_TIMEOUT_SECONDS = int(env("JOB_TIMEOUT_SECONDS", "1800"))
# rq: 로컬/상시 worker, cloudtasks: Cloud Run(worker를 HTTP로 호출, scale-to-zero)
QUEUE_BACKEND = env("QUEUE_BACKEND", "rq")
GCP_PROJECT = env("GCP_PROJECT", "")
GCP_LOCATION = env("GCP_LOCATION", "asia-northeast3")
TASKS_QUEUE = env("TASKS_QUEUE", "media")
WORKER_URL = env("WORKER_URL", "")  # Cloud Run worker service URL
TASKS_SERVICE_ACCOUNT = env("TASKS_SERVICE_ACCOUNT", "")  # worker 호출용 OIDC 토큰 발급 계정
# 테스트에서 RQ 작업을 요청 스레드에서 동기 실행한다.
RQ_SYNC = env("RQ_SYNC", "false") == "true"

SUPPORTED_EXTENSIONS = {
    "mp4", "mov", "avi", "wmv", "mkv", "flv",
    "mp3", "aac", "ac3", "ogg", "flac", "wav", "m4a",
}
