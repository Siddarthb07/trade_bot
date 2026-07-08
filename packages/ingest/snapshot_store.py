"""Persist market snapshots and EOD prices."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from core.models import EodPrice, MarketSnapshot


def upsert_snapshot(
  db: Session,
  *,
  source: str,
  snapshot_key: str,
  as_of: datetime,
  payload: dict[str, Any],
  market: str | None = None,
) -> tuple[MarketSnapshot, bool]:
  existing = (
    db.query(MarketSnapshot)
    .filter(MarketSnapshot.source == source, MarketSnapshot.snapshot_key == snapshot_key)
    .first()
  )
  if existing:
    existing.as_of = as_of
    existing.payload = payload
    if market:
      existing.market = market
    db.commit()
    db.refresh(existing)
    return existing, False

  row = MarketSnapshot(
    id=uuid.uuid4(),
    source=source,
    snapshot_key=snapshot_key,
    market=market,
    as_of=as_of,
    payload=payload,
  )
  db.add(row)
  db.commit()
  db.refresh(row)
  return row, True


def upsert_eod_prices(
  db: Session,
  rows: list[dict[str, Any]],
  *,
  market: str,
  trade_date: date,
  source: str,
) -> tuple[int, int]:
  """Insert EOD rows; skip duplicates. Returns (inserted, skipped)."""
  from core.tickers import display_ticker, normalize_ticker

  inserted = 0
  skipped = 0
  for row in rows:
    ticker = str(row["ticker"]).strip().upper()
    if not ticker:
      continue
    existing = (
      db.query(EodPrice)
      .filter(
        EodPrice.market == market.upper(),
        EodPrice.ticker == ticker,
        EodPrice.trade_date == trade_date,
        EodPrice.source == source,
      )
      .first()
    )
    if existing:
      skipped += 1
      continue
    db.add(
      EodPrice(
        id=uuid.uuid4(),
        market=market.upper(),
        ticker=display_ticker(ticker, market),
        ticker_normalized=normalize_ticker(ticker, market),
        trade_date=trade_date,
        close=float(row["close"]),
        volume=int(row["volume"]) if row.get("volume") is not None else None,
        source=source,
      )
    )
    inserted += 1
  db.commit()
  return inserted, skipped
