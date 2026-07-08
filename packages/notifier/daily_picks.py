"""Daily curated investment picks for WhatsApp group."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.config import get_settings
from core.db import SessionLocal
from core.models import AlertLog
from notifier.ntfy import send_ntfy
from notifier.ranking import collect_unified_ranked_picks
from notifier.templates import daily_picks_message
from notifier.waha import send_whatsapp, waha_healthy
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
settings = get_settings()
IST = ZoneInfo("Asia/Kolkata")


def send_daily_picks(market: str = "IN", *, force: bool = False) -> dict:
  if not settings.alerts_enabled or not settings.daily_picks_enabled:
    return {"sent": False, "reason": "disabled"}

  db = SessionLocal()
  try:
    day_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    unified = collect_unified_ranked_picks(
      db,
      market,
      limit=settings.daily_picks_max,
      days=14,
    )

    dedup = f"daily_picks:{market}:{day_start.date().isoformat()}"
    if not force and db.query(AlertLog).filter(AlertLog.dedup_key == dedup).first():
      return {"sent": False, "reason": "already_sent_today", "candidates": len(unified)}

    url = settings.dashboard_public_url.rstrip("/")
    text = daily_picks_message([], url, market=market, unified=unified)

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
      "picks": len(unified),
      "theme_picks": sum(1 for row in unified if row["kind"] == "Demand"),
      "candidates": len(unified),
      "market": market,
      "ranked_by": "investor_backing_then_expected_return",
    }
  finally:
    db.close()
