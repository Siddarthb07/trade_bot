"""Ingest macro / world-affairs theme stock picks."""

from __future__ import annotations

import logging

from core.config import get_settings
from core.db import SessionLocal
from core.queue import enqueue_process_batch
from ingest.common import finish_ingestion_run, start_ingestion_run, upsert_signal
from processor.macro_themes import SOURCE, build_signal_payload, rank_all_picks

logger = logging.getLogger(__name__)
settings = get_settings()


def ingest_macro_themes(*, market: str | None = None) -> dict:
  if not settings.macro_themes_enabled:
    return {"rows_in": 0, "rows_new": 0, "skipped": "disabled"}

  db = SessionLocal()
  run = start_ingestion_run(db, "ingest_macro_themes")
  new_ids: list[str] = []
  picks = rank_all_picks(market=market, min_composite=settings.macro_themes_min_composite)
  rows_in = len(picks)
  try:
    for pick in picks[: settings.macro_themes_max_signals]:
      payload = build_signal_payload(pick)
      signal, created = upsert_signal(db, payload)
      if created and signal:
        new_ids.append(str(signal.id))
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids))
  except Exception as exc:
    logger.exception("Macro theme ingest failed: %s", exc)
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids), status="failed", error=str(exc))
    raise
  finally:
    db.close()

  enqueue_process_batch(new_ids)
  return {"rows_in": rows_in, "rows_new": len(new_ids), "source": SOURCE}
