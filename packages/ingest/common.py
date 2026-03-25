"""Ingestion helpers."""

import json
import math
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.models import IngestionRun, Signal
from core.tickers import display_ticker, normalize_entity, normalize_ticker


def _sanitize_json(value):
  if value is None:
    return None
  if isinstance(value, float) and math.isnan(value):
    return None
  if isinstance(value, dict):
    return {str(k): _sanitize_json(v) for k, v in value.items() if _sanitize_json(v) is not None}
  if isinstance(value, list):
    return [_sanitize_json(v) for v in value if _sanitize_json(v) is not None]
  if isinstance(value, str) and value.lower() in ("nan", "no records", ""):
    return None
  return value


def is_valid_payload(payload: dict) -> bool:
  ticker = str(payload.get("ticker", "")).strip().upper()
  entity = str(payload.get("entity", "")).strip().upper()
  if not ticker or ticker in ("NAN", "UNKNOWN", "NO RECORDS"):
    return False
  if not entity or entity in ("NAN", "UNKNOWN"):
    return False
  if str(payload.get("action", "")).upper() in ("NAN", ""):
    return False
  return True


def start_ingestion_run(db: Session, job_name: str) -> IngestionRun:
    run = IngestionRun(job_name=job_name, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_ingestion_run(
    db: Session,
    run: IngestionRun,
    *,
    rows_in: int,
    rows_new: int,
    status: str = "success",
    error: str | None = None,
) -> None:
    run.finished_at = datetime.now(timezone.utc)
    run.rows_in = rows_in
    run.rows_new = rows_new
    run.status = status
    run.error = error
    db.commit()


def upsert_signal(db: Session, payload: dict) -> tuple[Signal | None, bool]:
    if not is_valid_payload(payload):
        return None, False
    existing = (
        db.query(Signal)
        .filter(Signal.source == payload["source"], Signal.source_ref == payload["source_ref"])
        .first()
    )
    if existing:
        return existing, False

    market = payload["market"]
    ticker = payload["ticker"]
    entity = payload["entity"]
    signal = Signal(
        id=uuid.uuid4(),
        source=payload["source"],
        source_ref=payload["source_ref"],
        market=market,
        entity=entity,
        entity_normalized=normalize_entity(entity),
        ticker=display_ticker(ticker, market),
        ticker_normalized=normalize_ticker(ticker, market),
        action=payload["action"].upper(),
        qty=payload.get("qty"),
        value=payload.get("value"),
        disclosed_at=payload["disclosed_at"],
        source_url=payload.get("source_url"),
        raw_json=_sanitize_json(payload.get("raw_json")),
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal, True
