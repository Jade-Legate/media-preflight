"""Media worker.

- 로컬/상시 실행: python -m preflight.worker  (Redis Queue를 소비)
- Cloud Run: uvicorn preflight.worker:app  (Cloud Tasks/Scheduler가 HTTP로 호출, 비공개 서비스)
"""

import threading
import time

from fastapi import FastAPI
from pydantic import BaseModel

from . import config
from .db import init_db
from .jobqueue import TASKS
from .tasks import cleanup_expired, log

app = FastAPI(title="Media Preflight Worker", on_startup=[init_db])


class TaskBody(BaseModel):
    id: str | None = None


@app.post("/tasks/{name}")
def run_task(name: str, body: TaskBody):
    # 작업 내부 오류는 DB에 FAILED로 기록하고 200을 반환한다 → Cloud Tasks가 같은 실패를 재시도하지 않는다.
    # 컨테이너가 죽는 등 응답을 못 준 경우에만 Cloud Tasks가 재시도한다.
    fn = TASKS.get(name)
    if not fn:
        return {"ok": False, "error": "UNKNOWN_TASK"}
    fn() if name == "cleanup" else fn(body.id)
    return {"ok": True}


def _cleanup_loop():
    while True:
        try:
            cleanup_expired()
        except Exception as e:  # noqa: BLE001 — cleanup 실패가 worker를 죽이면 안 된다
            log("cleanup_error", error=repr(e))
        time.sleep(3600)


if __name__ == "__main__":
    from redis import Redis
    from rq import Queue, Worker

    init_db()
    threading.Thread(target=_cleanup_loop, daemon=True).start()
    conn = Redis.from_url(config.REDIS_URL)
    Worker([Queue("media", connection=conn)], connection=conn).work()
