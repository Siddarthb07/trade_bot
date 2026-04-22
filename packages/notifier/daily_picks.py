"""Daily curated investment picks for WhatsApp group."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc

from core.config import get_settings
from core.db import SessionLocal
from core.models import AlertLog, Signal, SignalScore
from notifier.ntfy import send_ntfy
from notifier.templates import daily_picks_message
from notifier.waha import send_whatsapp, waha_healthy
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
settings = get_settings()
IST = ZoneInfo("Asia/Kolkata")


def _latest_score(db, signal_id) -> SignalScore | None:
  return (
    db.query(SignalScore)
    .filter(SignalScore.signal_id == signal_id)
    .order_by(desc(SignalScore.scored_at))
    .first()
  )


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


def _expected_return(score: SignalScore) -> float:
  dist = score.return_distribution or {}
  return float(dist.get("expected_return_pct") or 0)


def _theme_picks(db, market: str) -> list[tuple[Signal, SignalScore]]:
  if not settings.macro_themes_enabled:
    return []
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
  seen_tickers: set[str] = set()
  for signal in signals:
    if market and signal.market != market:
      continue
    if signal.ticker in seen_tickers:
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
  ranked.sort(key=lambda x: x[2], reverse=True)
  out: list[tuple[Signal, SignalScore]] = []
  for signal, score, _ in ranked:
    if signal.ticker in seen_tickers:
      continue
    seen_tickers.add(signal.ticker)
    out.append((signal, score))
    if len(out) >= settings.macro_themes_whatsapp_max:
      break
  return out


def send_daily_picks(market: str = "IN", *, force: bool = False) -> dict:
  if not settings.alerts_enabled or not settings.daily_picks_enabled:
    return {"sent": False, "reason": "disabled"}

  db = SessionLocal()
  try:
    day_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = day_start.astimezone(timezone.utc)
    signals = (
      db.query(Signal)
      .filter(
        Signal.market == market,
        Signal.disclosed_at >= day_start_utc - timedelta(hours=6),
        Signal.source.in_(["nse_bulk", "nse_block"]),
      )
      .order_by(desc(Signal.disclosed_at))
      .all()
    )

    candidates: list[tuple[Signal, SignalScore, float]] = []
    for signal in signals:
      score = _latest_score(db, signal.id)
      if score is None or not _is_buy_candidate(signal, score):
        continue
      candidates.append((signal, score, _expected_return(score)))

    candidates.sort(key=lambda x: x[2], reverse=True)
    top = [(s, sc) for s, sc, _ in candidates[: settings.daily_picks_max]]
    theme_top = _theme_picks(db, market)

    dedup = f"daily_picks:{market}:{day_start.date().isoformat()}"
    if not force and db.query(AlertLog).filter(AlertLog.dedup_key == dedup).first():
      return {"sent": False, "reason": "already_sent_today", "candidates": len(candidates)}

    url = settings.dashboard_public_url.rstrip("/")
    text = daily_picks_message(top, url, market=market, theme_picks=theme_top)

    if force:
      db.query(AlertLog).filter(AlertLog.dedup_key == dedup).delete()
      db.commit()

    log = AlertLog(dedup_key=dedup, channel="whatsapp", payload=text, status="pending")
    db.add(log)
    db.commit()

    sent = send_whatsapp(text) if waha_healthy() else send_ntfy(text)
    log.channel = "whatsapp" if waha_healthy() else "ntfy"
    log.status = "sent" if sent else "failed"
    log.sent_at = datetime.now(timezone.utc) if sent else None
    db.commit()

    return {
      "sent": sent,
      "picks": len(top),
      "theme_picks": len(theme_top),
      "candidates": len(candidates),
      "market": market,
      "ranked_by": "expected_return_pct",
    }
  finally:
    db.close()
