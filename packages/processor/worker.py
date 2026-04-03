"""RQ worker entrypoint."""

import os

import redis
from rq import Queue, Worker

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
conn = redis.from_url(redis_url)
queue = Queue("smartmoney", connection=conn)


def main() -> None:
  worker = Worker([queue], connection=conn)
  worker.work()


if __name__ == "__main__":
  main()
