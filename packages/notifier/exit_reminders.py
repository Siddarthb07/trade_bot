"""Exit and review reminders for active picks (Phase 1.4)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc

from core.config import get_settings
from core.db import SessionLocal
from core.models import AlertLog, Signal, SignalScore
from notifier.links import signal_dashboard_url
from notifier.ntfy import send_ntfy
from notifier.waha import send_whatsapp, waha_healthy

logger = logging.getLogger(__name__)
settings = get_settings()


def _latest_score(db, signal_id) -> SignalScore | None:
  return (
    db.query(SignalScore)
    .filter(SignalScore.signal_id == signal_id)
    .order_by(desc(SignalScore.scored_at))
    .first()
  )


def _timeframe_lines(dist: dict) -> list[str]:
  lines = []
  if dist.get("hold_label_long"):
    lines.append(f"HOLD: {dist['hold_label_long']}")
  elif dist.get("hold_days"):
    lines.append(f"HOLD: {dist['hold_days']} days")
  if dist.get("exit_date_label"):
    lines.append(f"SELL BY: {dist.get('exit_date_full') or dist['exit_date_label']}")
  if dist.get("review_date_label"):
    lines.append(f"REVIEW: {dist['review_date_label']} (mid-hold)")
  exp = dist.get("expected_return_pct")
  if exp is not None:
    lines.append(f"Est +{float(exp) * 100:.0f}% · not guaranteed")
  return lines


def send_exit_reminders() -> dict:
  db = SessionLocal()
  from core.hold_prefs import effective_hold_prefs

  prefs = effective_hold_prefs(db)
  if not settings.alerts_enabled or not prefs.exit_reminders_enabled:
    db.close()
    return {"sent": 0, "skipped": "disabled"}

  sent = 0
  now = datetime.now(timezone.utc)
  since = now - timedelta(days=120)
  try:
    signals = (
      db.query(Signal)
      .filter(
        Signal.disclosed_at >= since,
        Signal.action.in_(["BUY", "P", "A"]),
      )
      .all()
    )
    for signal in signals:
      score = _latest_score(db, signal.id)
      if not score or not score.return_distribution:
        continue
      dist = score.return_distribution
      hold_days = dist.get("hold_days") or dist.get("sell_horizon_days")
      if not hold_days:
        continue

      status = dist.get("hold_status")
      if status not in ("review_due", "exit_window", "overdue"):
        continue

      kind = "review" if status == "review_due" else "exit" if status == "exit_window" else "overdue"
      dedup = f"exit_reminder:{signal.id}:{kind}:{now.date().isoformat()}"
      if db.query(AlertLog).filter(AlertLog.dedup_key == dedup).first():
        continue

      url = signal_dashboard_url(str(signal.id), settings.dashboard_public_url)
      title = {"review": "Review", "exit": "Exit window", "overdue": "Overdue exit"}.get(kind, "Reminder")
      lines = [
        f"Trade Bot · {title} · {signal.ticker} · {signal.market}",
        *_timeframe_lines(dist),
      ]
      lines.extend(["Open pick", url])
      text = "\n".join(lines)[:900]

      log = AlertLog(dedup_key=dedup, channel="pending", payload=text, status="pending")
      db.add(log)
      db.commit()

      ok = send_whatsapp(text) if waha_healthy() else send_ntfy(text)
      log.channel = "whatsapp" if waha_healthy() else "ntfy"
      log.status = "sent" if ok else "failed"
      log.sent_at = datetime.now(timezone.utc) if ok else None
      db.commit()
      if ok:
        sent += 1
  finally:
    db.close()
  return {"sent": sent}
