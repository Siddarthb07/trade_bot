#!/usr/bin/env python3
"""Repair disclosed_at when NSE CSV BOM mangled the Date column."""

from __future__ import annotations

from sqlalchemy import Date, cast, func

from core.db import SessionLocal
from core.models import Signal
from ingest.nse_client import _make_ref, _parse_date, _to_float


def _extract_date(raw: dict) -> str | None:
  if not raw:
    return None
  for key, value in raw.items():
    key_norm = str(key).replace("\ufeff", "").strip().strip('"').strip().lower()
    if "date" in key_norm:
      return None if value is None else str(value)
  return None


def _extract_price(raw: dict) -> float | None:
  for key, value in raw.items():
    key_norm = str(key).lower()
    if "price" in key_norm or "wght" in key_norm:
      price = _to_float(value)
      if price is not None:
        return price
  return None


def main() -> None:
  db = SessionLocal()
  fixed = 0
  skipped = 0
  try:
    ids = [
      row[0]
      for row in db.query(Signal.id)
      .filter(
        Signal.source.in_(["nse_bulk", "nse_block"]),
        Signal.market == "IN",
      )
      .all()
    ]
    print({"candidates": len(ids)})
    for i in range(0, len(ids), 500):
      batch = (
        db.query(Signal)
        .filter(Signal.id.in_(ids[i : i + 500]))
        .all()
      )
      for signal in batch:
        raw = signal.raw_json or {}
        has_good = ("Date" in raw) or ("DATE" in raw)
        mangled = any(
          "date" in str(key).lower() and key not in ("Date", "DATE") for key in raw
        )
        if has_good and not mangled:
          skipped += 1
          continue
        date_val = _extract_date(raw)
        if not date_val:
          skipped += 1
          continue
        disclosed = _parse_date(date_val)
        if (
          signal.disclosed_at
          and signal.disclosed_at.date() == disclosed.date()
          and abs((signal.disclosed_at - disclosed).total_seconds()) < 86400
        ):
          skipped += 1
          continue
        price = _extract_price(raw)
        signal.disclosed_at = disclosed
        signal.source_ref = _make_ref(
          signal.source,
          signal.ticker or "",
          signal.entity or "",
          signal.action or "BUY",
          disclosed,
          signal.qty,
          price,
        )
        fixed += 1
      db.commit()
      print({"fixed": fixed, "skipped": skipped, "batch_end": i + len(batch)})

    days = (
      db.query(cast(Signal.disclosed_at, Date), func.count())
      .filter(Signal.source.in_(["nse_bulk", "nse_block"]))
      .group_by(cast(Signal.disclosed_at, Date))
      .order_by(cast(Signal.disclosed_at, Date))
      .all()
    )
    print(
      {
        "fixed": fixed,
        "skipped": skipped,
        "unique_days": len(days),
        "from": str(days[0][0]) if days else None,
        "to": str(days[-1][0]) if days else None,
        "first5": [(str(d), c) for d, c in days[:5]],
        "last5": [(str(d), c) for d, c in days[-5:]],
      }
    )
  finally:
    db.close()


if __name__ == "__main__":
  main()
