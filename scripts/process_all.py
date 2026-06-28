#!/usr/bin/env python3
"""Process all signals in small batches (low memory)."""

from __future__ import annotations

import os

os.environ.setdefault("NOTIFY_DRY_RUN", "true")

import logging

from core.db import SessionLocal
from core.models import Signal
from processor.jobs import process_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH = int(os.environ.get("PROCESS_BATCH_SIZE", "10"))


def main() -> None:
  db = SessionLocal()
  ids = [str(s.id) for s in db.query(Signal.id).all()]
  db.close()
  logger.info("Processing %s signals in batches of %s (dry-run alerts)", len(ids), BATCH)
  total = 0
  for i in range(0, len(ids), BATCH):
    batch = ids[i : i + BATCH]
    result = process_batch(batch)
    total += result["processed"]
    logger.info("Batch %s/%s done (%s processed)", min(i + BATCH, len(ids)), len(ids), result["processed"])
  logger.info("Finished. Total processed: %s", total)


if __name__ == "__main__":
  main()
