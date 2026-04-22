"""Alert dispatch with dedup, prefs, and strict quality gates."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import redis

from core.config import get_settings
from core.models import AlertLog, AlertPrefs, InvestorStat, Signal, SignalScore
from notifier.ntfy import send_ntfy
from notifier.templates import brief_whatsapp_message
from notifier.waha import send_whatsapp, waha_healthy
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
settings = get_settings()
IST = ZoneInfo("Asia/Kolkata")
TIER_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def backfill_gate_passed(db: Session) -> bool:
  if settings.alerts_enabled:
    return True
  in_count = db.query(Signal).filter(Signal.market == "IN").count()
  entity_count = (
    db.query(InvestorStat)
    .filter(InvestorStat.market == "IN", InvestorStat.n_trades >= settings.backfill_min_entity_trades)
    .count()
  )
  return in_count >= settings.backfill_min_signals and entity_count >= settings.backfill_min_entities


def _get_prefs(db: Session) -> AlertPrefs:
  prefs = db.query(AlertPrefs).filter(AlertPrefs.id == 1).first()
  if prefs is None:
    prefs = AlertPrefs()
    db.add(prefs)
    db.commit()
    db.refresh(prefs)
  return prefs


def _in_quiet_hours(prefs: AlertPrefs) -> bool:
  hour = datetime.now(IST).hour
  start = prefs.quiet_hours_start
  end = prefs.quiet_hours_end
  if start < end:
    return start <= hour < end
  return hour >= start or hour < end


def _dedup_key(signal: Signal, score: SignalScore) -> str:
  return f"{signal.market}:{signal.ticker}:{signal.entity_normalized}:{signal.disclosed_at.date()}:{score.tier}"


def _passes_quality_gate(signal: Signal, score: SignalScore) -> bool:
  dist = score.return_distribution or {}
  prob = dist.get("calibrated_probability")
  exp = dist.get("expected_return_pct")

  if settings.alert_buys_only and signal.action.upper() not in ("BUY", "P", "A"):
    return False
  if prob is None or prob < settings.alert_min_probability:
    return False
  if exp is None or exp < settings.alert_min_expected_return_pct:
    return False
  if signal.market == "IN" and (signal.value or 0) < settings.alert_min_deal_value_inr:
    return False
  if TIER_RANK.get(score.tier, 0) < TIER_RANK.get(settings.alert_instant_min_tier, 3):
    return False
  return True


def _should_notify(db: Session, signal: Signal, score: SignalScore) -> bool:
  if not settings.alert_instant_enabled:
    return False
  if not backfill_gate_passed(db):
    return False
  if not _passes_quality_gate(signal, score):
    return False
  prefs = _get_prefs(db)
  if signal.market == "IN" and not prefs.market_in:
    return False
  if signal.market == "US" and not prefs.market_us:
    return False
  if TIER_RANK.get(score.tier, 0) < TIER_RANK.get(prefs.min_tier, 2):
    return False
  if _in_quiet_hours(prefs):
    return False
  if signal.source == "sec_13f":
    return False
  return True


def dispatch_alert(db: Session, signal: Signal, score: SignalScore, text: str) -> bool:
  dedup = _dedup_key(signal, score)
  existing = db.query(AlertLog).filter(AlertLog.dedup_key == dedup).first()
  if existing:
    return False

  redis_client = redis.from_url(settings.redis_url)
  if not redis_client.setnx(f"alert:{dedup}", "1"):
    return False
  redis_client.expire(f"alert:{dedup}", 86400)

  log = AlertLog(dedup_key=dedup, channel="whatsapp", payload=text, status="pending")
  db.add(log)
  db.commit()

  sent = False
  channel = "whatsapp"
  if waha_healthy():
    sent = send_whatsapp(text)
  else:
    channel = "ntfy"
    sent = send_ntfy(text)

  log.channel = channel
  log.status = "sent" if sent else "failed"
  log.sent_at = datetime.now(timezone.utc) if sent else None
  log.retries = 0 if sent else 1
  db.commit()
  return sent


def maybe_notify_signal(db: Session, signal: Signal, score: SignalScore) -> bool:
  if not _should_notify(db, signal, score):
    return False
  text = brief_whatsapp_message(signal, score, settings.dashboard_public_url.rstrip("/"))
  return dispatch_alert(db, signal, score, text)
