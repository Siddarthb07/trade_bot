"""BSE bulk deal ingestion."""

from __future__ import annotations

import logging

from core.db import SessionLocal
from core.queue import enqueue_process_batch
from ingest.bse_client import BSEClient
from ingest.common import finish_ingestion_run, start_ingestion_run, upsert_signal

logger = logging.getLogger(__name__)


def ingest_bse_bulk(days: int = 7) -> dict:
    client = BSEClient()
    db = SessionLocal()
    run = start_ingestion_run(db, "ingest_bse_bulk")
    new_ids: list[str] = []
    payloads: list = []
    try:
        payloads = client.fetch_bulk_deals(days=days)
        rows_in = len(payloads)
        for payload in payloads:
            signal, created = upsert_signal(db, payload)
            if created and signal:
                new_ids.append(str(signal.id))
        finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids))
    except Exception as exc:
        logger.exception("BSE bulk ingest failed: %s", exc)
        finish_ingestion_run(db, run, rows_in=len(payloads), rows_new=len(new_ids), status="failed", error=str(exc))
        return {"rows_in": len(payloads), "rows_new": len(new_ids), "error": str(exc)}
    finally:
        db.close()
    enqueue_process_batch(new_ids)
    return {"rows_in": len(payloads), "rows_new": len(new_ids)}
