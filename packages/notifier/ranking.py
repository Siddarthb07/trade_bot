"""Unified pick ranking for WhatsApp digests and share landing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import Signal, SignalScore
from processor.confluence import bulk_confluence

settings = get_settings()


def _latest_score(db: Session, signal_id) -> SignalScore | None:
  return (
    db.query(SignalScore)
    .filter(SignalScore.signal_id == signal_id)
    .order_by(desc(SignalScore.scored_at))
    .first()
  )


def _expected_return(score: SignalScore | None) -> float:
  if not score:
    return 0.0
  dist = score.return_distribution or {}
  val = dist.get("expected_return_pct") or dist.get("composite_score")
  return float(val or 0)


def _is_buy_candidate(signal: Signal, score: SignalScore) -> bool:
  if signal.action.upper() not in ("BUY", "P", "A"):
    return False
  dist = score.return_distribution or {}
  exp = dist.get("expected_return_pct")
  if exp is None or float(exp) < settings.daily_picks_min_expected_return_pct:
    return False
  prob = dist.get("calibrated_probability")
  if prob is not None and float(prob) < settings.daily_picks_min_probability:
    return False
  return True


def _rank_key(*, investor_count: int, expected: float) -> tuple[int, int, float]:
  return (1 if investor_count else 0, investor_count, expected)


def _bulk_candidates(
  db: Session,
  market: str,
  *,
  since: datetime,
) -> list[tuple[Signal, SignalScore, float, int, int]]:
  signals = (
    db.query(Signal)
    .filter(
      Signal.market == market.upper(),
      Signal.disclosed_at >= since,
      Signal.source.in_(["nse_bulk", "nse_block", "bse_bulk"]),
    )
    .order_by(desc(Signal.disclosed_at))
    .all()
  )
  deal_counts: dict[str, int] = {}
  ranked: list[tuple[float, Signal, SignalScore, int]] = []
  for signal in signals:
    if signal.action.upper() not in ("BUY", "P", "A"):
      continue
    deal_counts[signal.ticker] = deal_counts.get(signal.ticker, 0) + 1
    score = _latest_score(db, signal.id)
    if score is None or not _is_buy_candidate(signal, score):
      continue
    ranked.append((_expected_return(score), signal, score, deal_counts[signal.ticker]))

  best: dict[str, tuple[float, Signal, SignalScore, int]] = {}
  for exp, signal, score, n in ranked:
    prev = best.get(signal.ticker)
    if prev is None or exp > prev[0]:
      best[signal.ticker] = (exp, signal, score, n)

  out: list[tuple[Signal, SignalScore, float, int, int]] = []
  for ticker, (exp, signal, score, n) in best.items():
    week = bulk_confluence(db, ticker, market.upper(), since_days=7)
    out.append((signal, score, exp, n, week["bulk_deal_count"]))
  return out


def _theme_candidates(db: Session, market: str) -> list[tuple[Signal, SignalScore, float]]:
  if not settings.macro_themes_enabled:
    return []

  from zoneinfo import ZoneInfo

  IST = ZoneInfo("Asia/Kolkata")
  day_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
  day_start_utc = day_start.astimezone(timezone.utc)
  signals = (
    db.query(Signal)
    .filter(
      Signal.source == "macro_theme",
      Signal.disclosed_at >= day_start_utc - timedelta(hours=12),
    )
    .all()
  )
  ranked: list[tuple[Signal, SignalScore, float]] = []
  for signal in signals:
    if market and signal.market != market.upper():
      continue
    score = _latest_score(db, signal.id)
    if score is None:
      continue
    dist = score.return_distribution or {}
    prob = dist.get("calibrated_probability")
    if prob is not None and float(prob) < settings.macro_themes_min_probability:
      continue
    composite = float(dist.get("composite_score") or dist.get("expected_return_pct") or 0)
    ranked.append((signal, score, composite))
  return ranked


def collect_unified_ranked_picks(
  db: Session,
  market: str = "IN",
  *,
  limit: int = 10,
  days: int = 14,
) -> list[dict[str, Any]]:
  """Merge bulk + theme picks, dedupe by ticker, rank, assign rank_index."""
  since = datetime.now(timezone.utc) - timedelta(days=days)
  merged: dict[str, dict[str, Any]] = {}

  for signal, score, exp, deal_n, week_n in _bulk_candidates(db, market, since=since):
    key = f"{signal.market}:{signal.ticker}"
    conf = bulk_confluence(db, signal.ticker, signal.market, since_days=30)
    investor_count = conf.get("bulk_deal_count") or 0
    if conf.get("has_bulk_deal"):
      investor_count = max(investor_count, 1)
    entry = {
      "signal": signal,
      "score": score,
      "kind": "Bulk",
      "expected_return_pct": exp,
      "bulk_deal_count": deal_n,
      "bulk_deal_count_week": week_n,
      "investor_count": investor_count,
      "theme_name": None,
    }
    prev = merged.get(key)
    if prev is None or exp > prev["expected_return_pct"]:
      merged[key] = entry

  for signal, score, exp in _theme_candidates(db, market):
    key = f"{signal.market}:{signal.ticker}"
    raw = signal.raw_json or {}
    conf = bulk_confluence(db, signal.ticker, signal.market, since_days=30)
    investor_count = conf["bulk_deal_count"] if conf.get("bulk_confirmed") else 0
    entry = {
      "signal": signal,
      "score": score,
      "kind": "Demand",
      "expected_return_pct": exp,
      "bulk_deal_count": conf.get("bulk_deal_count") or 0,
      "bulk_deal_count_week": bulk_confluence(db, signal.ticker, signal.market, since_days=7)["bulk_deal_count"],
      "investor_count": investor_count,
      "theme_name": raw.get("theme_name") or signal.entity,
    }
    prev = merged.get(key)
    if prev is None or _rank_key(investor_count=investor_count, expected=exp) > _rank_key(
      investor_count=prev["investor_count"], expected=prev["expected_return_pct"]
    ):
      merged[key] = entry

  ordered = sorted(
    merged.values(),
    key=lambda row: _rank_key(
      investor_count=row["investor_count"],
      expected=row["expected_return_pct"],
    ),
    reverse=True,
  )[:limit]

  for idx, row in enumerate(ordered, start=1):
    row["rank_index"] = idx
  return ordered
