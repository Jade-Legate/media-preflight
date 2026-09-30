"""Media worker entrypoint: python -m preflight.worker"""

import threading
import time

from redis import Redis
from rq import Queue, Worker

from . import config
from .db import init_db
from .tasks import cleanup_expired, log


def _cleanup_loop():
    while True:
        try:
            cleanup_expired()
        except Exception as e:  # noqa: BLE001 — cleanup 실패가 worker를 죽이면 안 된다
            log("cleanup_error", error=repr(e))
        time.sleep(3600)


if __name__ == "__main__":
    init_db()
    threading.Thread(target=_cleanup_loop, daemon=True).start()
    conn = Redis.from_url(config.REDIS_URL)
    Worker([Queue("media", connection=conn)], connection=conn).work()
