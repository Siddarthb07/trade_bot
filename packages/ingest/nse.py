"""NSE ingestion orchestration."""

from __future__ import annotations

import logging

from core.db import SessionLocal
from core.queue import enqueue_process_batch
from ingest.common import finish_ingestion_run, start_ingestion_run, upsert_signal
from ingest.nse_client import NSEClient

logger = logging.getLogger(__name__)


def ingest_nse(job_name: str = "ingest_nse_eod") -> dict:
  client = NSEClient()
  db = SessionLocal()
  run = start_ingestion_run(db, job_name)
  rows_in = 0
  new_ids: list[str] = []
  try:
    payloads: list[dict] = []
    for mode in ("bulk_deals", "block_deals"):
      try:
        payloads.extend(client.fetch_live_deals(mode))
      except Exception as exc:
        logger.exception("Live NSE fetch failed for %s: %s", mode, exc)
    rows_in = len(payloads)
    for payload in payloads:
      signal, created = upsert_signal(db, payload)
      if created and signal:
        new_ids.append(str(signal.id))
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids))
  except Exception as exc:
    logger.exception("NSE ingest failed: %s", exc)
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids), status="failed", error=str(exc))
    raise
  finally:
    db.close()
  enqueue_process_batch(new_ids)
  return {"rows_in": rows_in, "rows_new": len(new_ids)}


def ingest_nse_block_intraday() -> dict:
  return ingest_nse("ingest_nse_block_intraday")


def ingest_nse_eod() -> dict:
  return ingest_nse("ingest_nse_eod")


def backfill_nse_archive(limit: int | None = 2000) -> dict:
  client = NSEClient()
  db = SessionLocal()
  run = start_ingestion_run(db, "backfill_nse")
  new_ids: list[str] = []
  rows_in = 0
  try:
    payloads: list[dict] = []
    for mode in ("bulk_deals", "block_deals"):
      payloads.extend(client.fetch_archive_csv(mode))
    if limit:
      payloads = payloads[:limit]
    rows_in = len(payloads)
    for payload in payloads:
      signal, created = upsert_signal(db, payload)
      if created and signal:
        new_ids.append(str(signal.id))
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids))
  except Exception as exc:
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids), status="failed", error=str(exc))
    raise
  finally:
    db.close()
  enqueue_process_batch(new_ids)
  return {"rows_in": rows_in, "rows_new": len(new_ids)}


def ingest_nse_payloads(payloads: list[dict]) -> dict:
  db = SessionLocal()
  run = start_ingestion_run(db, "host_nse_fallback")
  new_ids: list[str] = []
  try:
    for payload in payloads:
      signal, created = upsert_signal(db, payload)
      if created and signal:
        new_ids.append(str(signal.id))
    finish_ingestion_run(db, run, rows_in=len(payloads), rows_new=len(new_ids))
  except Exception as exc:
    finish_ingestion_run(db, run, rows_in=len(payloads), rows_new=len(new_ids), status="failed", error=str(exc))
    raise
  finally:
    db.close()
  enqueue_process_batch(new_ids)
  return {"rows_in": len(payloads), "rows_new": len(new_ids)}
