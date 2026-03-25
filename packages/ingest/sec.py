"""SEC EDGAR ingestion via edgartools."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

from edgar import Company, get_filings, set_identity

from core.config import get_settings
from core.db import SessionLocal
from core.queue import enqueue_process_batch
from ingest.common import finish_ingestion_run, start_ingestion_run, upsert_signal

logger = logging.getLogger(__name__)
settings = get_settings()


def _ensure_identity() -> None:
  os.environ.setdefault("EDGAR_IDENTITY", settings.sec_identity)
  set_identity(settings.sec_identity)


def _make_ref(accession: str, ticker: str, entity: str, action: str) -> str:
  raw = f"{accession}|{ticker}|{entity}|{action}"
  return hashlib.sha256(raw.encode()).hexdigest()[:32]


def ingest_form4() -> dict:
  _ensure_identity()
  db = SessionLocal()
  run = start_ingestion_run(db, "ingest_sec_form4")
  new_ids: list[str] = []
  rows_in = 0
  try:
    filings = get_filings(form="4").head(100)
    rows_in = len(filings)
    for filing in filings:
      try:
        form4 = filing.obj()
        issuer = getattr(form4, "issuer", None)
        ticker = getattr(issuer, "ticker", None) or getattr(issuer, "symbol", None) or "UNKNOWN"
        entity = filing.company or getattr(issuer, "name", "UNKNOWN")
        for tx in getattr(form4, "transactions", []) or []:
          action = str(getattr(tx, "code", "P")).upper()
          if action in ("P", "A"):
            action_label = "BUY"
          elif action in ("S", "D"):
            action_label = "SELL"
          else:
            action_label = action
          qty = float(getattr(tx, "shares", 0) or 0)
          price = float(getattr(tx, "price", 0) or 0)
          value = qty * price if qty and price else None
          disclosed = getattr(filing, "filing_date", None) or datetime.now(timezone.utc)
          if not isinstance(disclosed, datetime):
            disclosed = datetime.combine(disclosed, datetime.min.time(), tzinfo=timezone.utc)
          payload = {
            "source": "sec_form4",
            "source_ref": _make_ref(filing.accession_number, ticker, entity, action_label),
            "market": "US",
            "entity": entity,
            "ticker": ticker,
            "action": action_label,
            "qty": qty,
            "value": value,
            "disclosed_at": disclosed,
            "source_url": filing.filing_url,
            "raw_json": {"accession": filing.accession_number},
          }
          signal, created = upsert_signal(db, payload)
          if created and signal:
            new_ids.append(str(signal.id))
      except Exception as exc:
        logger.warning("Form4 parse failed for %s: %s", filing, exc)
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids))
  except Exception as exc:
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids), status="failed", error=str(exc))
    raise
  finally:
    db.close()
  enqueue_process_batch(new_ids)
  return {"rows_in": rows_in, "rows_new": len(new_ids)}


def ingest_13f() -> dict:
  _ensure_identity()
  db = SessionLocal()
  run = start_ingestion_run(db, "ingest_sec_13f")
  new_ids: list[str] = []
  rows_in = 0
  try:
    filings = get_filings(form="13F-HR").head(50)
    rows_in = len(filings)
    for filing in filings:
      try:
        report = filing.obj()
        entity = filing.company or "UNKNOWN"
        holdings = getattr(report, "holdings", None)
        if holdings is None:
          continue
        df = holdings if hasattr(holdings, "iterrows") else None
        if df is None:
          continue
        for _, row in df.iterrows():
          ticker = str(row.get("Ticker") or row.get("ticker") or "UNKNOWN")
          value = float(row.get("Value") or row.get("value") or 0)
          qty = float(row.get("Shares") or row.get("shares") or 0)
          disclosed = getattr(filing, "filing_date", None) or datetime.now(timezone.utc)
          if not isinstance(disclosed, datetime):
            disclosed = datetime.combine(disclosed, datetime.min.time(), tzinfo=timezone.utc)
          payload = {
            "source": "sec_13f",
            "source_ref": _make_ref(filing.accession_number, ticker, entity, "HOLD"),
            "market": "US",
            "entity": entity,
            "ticker": ticker,
            "action": "BUY",
            "qty": qty,
            "value": value,
            "disclosed_at": disclosed,
            "source_url": filing.filing_url,
            "raw_json": {"accession": filing.accession_number},
          }
          signal, created = upsert_signal(db, payload)
          if created and signal:
            new_ids.append(str(signal.id))
      except Exception as exc:
        logger.warning("13F parse failed for %s: %s", filing, exc)
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids))
  except Exception as exc:
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids), status="failed", error=str(exc))
    raise
  finally:
    db.close()
  enqueue_process_batch(new_ids)
  return {"rows_in": rows_in, "rows_new": len(new_ids)}


def backfill_sec(limit: int = 100) -> dict:
  _ensure_identity()
  db = SessionLocal()
  run = start_ingestion_run(db, "backfill_sec")
  new_ids: list[str] = []
  rows_in = 0
  try:
    filings = get_filings(form="4").head(limit)
    rows_in = len(filings)
    for filing in filings:
      try:
        form4 = filing.obj()
        issuer = getattr(form4, "issuer", None)
        ticker = getattr(issuer, "ticker", None) or "UNKNOWN"
        entity = filing.company or "UNKNOWN"
        payload = {
          "source": "sec_form4",
          "source_ref": _make_ref(filing.accession_number, ticker, entity, "BUY"),
          "market": "US",
          "entity": entity,
          "ticker": ticker,
          "action": "BUY",
          "qty": None,
          "value": None,
          "disclosed_at": datetime.now(timezone.utc),
          "source_url": filing.filing_url,
          "raw_json": {"accession": filing.accession_number},
        }
        signal, created = upsert_signal(db, payload)
        if created and signal:
          new_ids.append(str(signal.id))
      except Exception:
        continue
    finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(new_ids))
  except Exception as exc:
    finish_ingestion_run(db, run, rows_in=0, rows_new=len(new_ids), status="failed", error=str(exc))
    raise
  finally:
    db.close()
  enqueue_process_batch(new_ids)
  return {"rows_in": rows_in, "rows_new": len(new_ids)}
