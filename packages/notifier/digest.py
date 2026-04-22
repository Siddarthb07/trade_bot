"""Daily 13F digest notifications."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from core.config import get_settings
from core.db import SessionLocal
from core.models import Signal
from notifier.templates import digest_message
from notifier.waha import send_whatsapp, waha_healthy
from notifier.ntfy import send_ntfy

logger = logging.getLogger(__name__)
settings = get_settings()


def send_daily_digest() -> dict:
  if not settings.alerts_enabled:
    return {"sent": False, "reason": "alerts_disabled"}
  db = SessionLocal()
  try:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    filings = (
      db.query(Signal)
      .filter(Signal.source == "sec_13f", Signal.created_at >= since)
      .all()
    )
    if not filings:
      return {"sent": False, "reason": "no_new_13f"}
    entities: dict[str, int] = {}
    for row in filings:
      entities[row.entity] = entities.get(row.entity, 0) + 1
    top = sorted(entities.items(), key=lambda x: x[1], reverse=True)[:3]
    summary = " · ".join(f"{name} +{count}" for name, count in top)
    text = digest_message(len(filings), summary, settings.dashboard_public_url.rstrip("/"))
    sent = send_whatsapp(text) if waha_healthy() else send_ntfy(text)
    return {"sent": sent, "count": len(filings)}
  finally:
    db.close()
