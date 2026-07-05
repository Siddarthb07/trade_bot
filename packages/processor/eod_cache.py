"""Read end-of-day prices from Postgres (populated by pull_free / NSE ingest)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from core.models import EodPrice


def infer_market(ticker_normalized: str, market: str | None = None) -> str:
  if market:
    return market.upper()
  upper = ticker_normalized.upper()
  if upper.endswith(".NS") or upper.endswith(".BO"):
    return "IN"
  return "US"


def fetch_eod_history(
  db: Session,
  ticker_normalized: str,
  market: str,
  *,
  days: int = 180,
) -> list[dict]:
  cutoff = date.today() - timedelta(days=days)
  rows = (
    db.query(EodPrice)
    .filter(
      EodPrice.ticker_normalized == ticker_normalized,
      EodPrice.market == market.upper(),
      EodPrice.trade_date >= cutoff,
    )
    .order_by(EodPrice.trade_date.asc())
    .all()
  )
  return [
    {
      "date": row.trade_date.isoformat(),
      "close": round(float(row.close), 2),
      "volume": int(row.volume or 0),
    }
    for row in rows
  ]


def eod_row_count(db: Session, ticker_normalized: str, market: str, *, min_rows: int = 60) -> int:
  cutoff = date.today() - timedelta(days=365)
  n = (
    db.query(EodPrice)
    .filter(
      EodPrice.ticker_normalized == ticker_normalized,
      EodPrice.market == market.upper(),
      EodPrice.trade_date >= cutoff,
    )
    .count()
  )
  return n if n >= min_rows else 0
