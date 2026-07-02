"""Scheduled ML training pipeline (Phase 2.3)."""

from __future__ import annotations

import logging

from core.config import get_settings
from core.db import SessionLocal
from ingest.common import finish_ingestion_run, start_ingestion_run
from processor.train import rescore_all, train_model

logger = logging.getLogger(__name__)
settings = get_settings()


def run_scheduled_train(*, force: bool = False) -> dict:
  if not settings.ml_train_enabled and not force:
    return {"status": "skipped", "reason": "disabled"}

  db = SessionLocal()
  run = start_ingestion_run(db, "ml_scheduled_train")
  try:
    meta = train_model()

    rescored = 0
    if meta.get("status") == "trained":
      rescored = rescore_all()
      meta["rescored"] = rescored

    finish_ingestion_run(
      db,
      run,
      rows_in=meta.get("n_samples") or 0,
      rows_new=rescored,
      status="success" if meta.get("status") == "trained" else "skipped",
      error=None if meta.get("status") == "trained" else meta.get("reason"),
    )
    logger.info("ML train job: %s", meta)
    return meta
  except Exception as exc:
    logger.exception("ML train failed: %s", exc)
    finish_ingestion_run(db, run, rows_in=0, rows_new=0, status="failed", error=str(exc))
    raise
  finally:
    db.close()
