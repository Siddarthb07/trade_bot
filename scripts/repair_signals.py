#!/usr/bin/env python3
"""Repair signal fields from stored raw_json after parser fixes."""

from __future__ import annotations

import logging

from ingest.nse_client import _parse_date, _to_float
from core.db import SessionLocal
from core.models import ForwardReturn, Signal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _fields_from_raw(raw: dict) -> dict:
  qty = _to_float(raw.get("Quantity Traded") or raw.get("QUANTITY") or raw.get("Quantity"))
  price = _to_float(
    raw.get("Trade Price / Wght. Avg. Price")
    or raw.get("TRADE_PRICE")
    or raw.get("Trade Price")
    or raw.get("AVG_PRICE")
  )
  value = _to_float(raw.get("VALUE") or raw.get("Value"))
  if value is None and qty and price:
    value = qty * price
  disclosed = _parse_date(raw.get("Date") or raw.get("DATE"))
  return {"qty": qty, "value": value, "disclosed_at": disclosed}


def main() -> None:
  db = SessionLocal()
  updated = 0
  try:
    signals = db.query(Signal).filter(Signal.raw_json.isnot(None)).all()
    for signal in signals:
      raw = signal.raw_json or {}
      if not isinstance(raw, dict):
        continue
      fields = _fields_from_raw(raw)
      changed = False
      for key, val in fields.items():
        if val is not None and getattr(signal, key) != val:
          setattr(signal, key, val)
          changed = True
      if changed:
        updated += 1
    db.commit()
    db.query(ForwardReturn).delete()
    db.commit()
    logger.info("Repaired %s signals and cleared forward returns for recompute.", updated)
  finally:
    db.close()


if __name__ == "__main__":
  main()
