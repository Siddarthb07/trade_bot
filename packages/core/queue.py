"""Redis queue helpers."""

import redis
from rq import Queue, Retry

from core.config import get_settings

settings = get_settings()
redis_conn = redis.from_url(settings.redis_url)
task_queue = Queue("smartmoney", connection=redis_conn)


def enqueue_process_batch(signal_ids: list[str]) -> None:
    if not signal_ids:
        return
    task_queue.enqueue(
        "processor.jobs.process_batch",
        signal_ids,
        job_timeout=600,
        retry=Retry(max=3),
    )
