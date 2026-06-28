#!/usr/bin/env python3
"""Seed data from NSE, process, train ML model, rescore all signals."""

from __future__ import annotations

import logging

from core.db import SessionLocal
from core.models import Signal
from core.queue import enqueue_process_batch
from ingest.common import finish_ingestion_run, start_ingestion_run, upsert_signal
from ingest.nse import ingest_nse_eod
from ingest.nse_client import NSEClient
from processor.jobs import process_batch
from processor.train import rescore_all, train_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_bulk_only(limit: int = 2000) -> int:
  client = NSEClient()
  db = SessionLocal()
  run = start_ingestion_run(db, "seed_bulk")
  new_ids: list[str] = []
  try:
    payloads = client.fetch_archive_csv("bulk_deals")
    try:
      payloads.extend(client.fetch_live_deals("bulk_deals"))
    except Exception as exc:
      logger.warning("Live bulk fetch failed: %s", exc)
    payloads = payloads[: min(limit or 2000, 2000)]
    for payload in payloads:
      signal, created = upsert_signal(db, payload)
      if created and signal:
        new_ids.append(str(signal.id))
    finish_ingestion_run(db, run, rows_in=len(payloads), rows_new=len(new_ids))
  except Exception as exc:
    db.rollback()
    finish_ingestion_run(db, run, rows_in=0, rows_new=len(new_ids), status="failed", error=str(exc))
    raise
  finally:
    db.close()
  return len(new_ids)


def main() -> None:
  logger.info("Running live NSE ingest...")
  try:
    ingest_nse_eod()
  except Exception as exc:
    logger.warning("Live ingest: %s", exc)

  logger.info("Seeding bulk archive...")
  n = seed_bulk_only(2000)
  logger.info("Seeded %s new signals", n)

  db = SessionLocal()
  all_ids = [str(s.id) for s in db.query(Signal.id).all()]
  db.close()
  logger.info("Processing %s signals (returns + stats)...", len(all_ids))
  for i in range(0, len(all_ids), 50):
    batch = all_ids[i : i + 50]
    process_batch(batch)
    logger.info("Processed batch %s/%s", min(i + 50, len(all_ids)), len(all_ids))

  logger.info("Training LightGBM model...")
  metrics = train_model()
  logger.info("Train metrics: %s", metrics)

  logger.info("Rescoring all signals with ML model...")
  updated = rescore_all()
  logger.info("Rescored %s signals. Done.", updated)


if __name__ == "__main__":
  main()
