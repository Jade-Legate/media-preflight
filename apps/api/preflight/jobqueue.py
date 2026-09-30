"""작업 큐. 웹 요청은 enqueue만 하고 FFmpeg는 worker에서 실행한다."""

import json

from . import config, tasks

TASKS = {"diagnose": tasks.run_diagnostic, "fix": tasks.run_fix, "cleanup": tasks.cleanup_expired}

if config.QUEUE_BACKEND == "cloudtasks":
    from google.cloud import tasks_v2

    _client = tasks_v2.CloudTasksClient()
    _parent = _client.queue_path(config.GCP_PROJECT, config.GCP_LOCATION, config.TASKS_QUEUE)

    def enqueue(name: str, arg: str) -> None:
        _client.create_task(parent=_parent, task={
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{config.WORKER_URL}/tasks/{name}",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"id": arg}).encode(),
                # worker는 비공개 Cloud Run 서비스: Cloud Tasks가 OIDC 토큰으로 호출한다.
                "oidc_token": {"service_account_email": config.TASKS_SERVICE_ACCOUNT, "audience": config.WORKER_URL},
            },
            "dispatch_deadline": {"seconds": min(config.JOB_TIMEOUT_SECONDS, 1800)},
        })

    def ping() -> str:
        return "ok"

else:
    from redis import Redis
    from rq import Queue

    redis = Redis.from_url(config.REDIS_URL)
    _queue = Queue("media", connection=redis, is_async=not config.RQ_SYNC)

    def enqueue(name: str, arg: str) -> None:
        _queue.enqueue(TASKS[name], arg, job_timeout=config.JOB_TIMEOUT_SECONDS)

    def ping() -> str:
        redis.ping()
        return "ok"
