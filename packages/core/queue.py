"""Redis queue helpers with lazy connect + retry (avoids 502 on api restart)."""

from __future__ import annotations

import logging
import time

import redis
from rq import Queue, Retry

from core.config import get_settings

logger = logging.getLogger(__name__)

_redis_conn: redis.Redis | None = None
_task_queue: Queue | None = None


def get_redis() -> redis.Redis:
  global _redis_conn
  if _redis_conn is not None:
    return _redis_conn

  settings = get_settings()
  last_err: Exception | None = None
  for attempt in range(6):
    try:
      conn = redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
      conn.ping()
      _redis_conn = conn
      return conn
    except Exception as exc:
      last_err = exc
      wait = min(2 ** attempt, 8)
      logger.warning("Redis connect attempt %s failed: %s (retry in %ss)", attempt + 1, exc, wait)
      time.sleep(wait)

  assert last_err is not None
  raise last_err


def get_task_queue() -> Queue:
  global _task_queue
  if _task_queue is None:
    _task_queue = Queue("smartmoney", connection=get_redis())
  return _task_queue


def redis_ping() -> bool:
  try:
    get_redis().ping()
    return True
  except Exception:
    return False


def queue_depth() -> int | None:
  try:
    return len(get_task_queue())
  except Exception:
    return None


def enqueue_process_batch(signal_ids: list[str]) -> None:
  if not signal_ids:
    return
  get_task_queue().enqueue(
    "processor.jobs.process_batch",
    signal_ids,
    job_timeout=600,
    retry=Retry(max=3),
  )
