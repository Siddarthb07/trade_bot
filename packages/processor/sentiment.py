"""Optional social mention / sentiment heat (filter only)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from core.db import SessionLocal
from core.models import MarketSnapshot

logger = logging.getLogger(__name__)

TRADESTIE_URL = "https://api.tradestie.com/v1/apps/reddit"


def fetch_wsb_mentions() -> list[dict]:
  try:
    with httpx.Client(timeout=15) as client:
      r = client.get(TRADESTIE_URL)
      if r.status_code >= 400:
        return []
      data = r.json()
      return data if isinstance(data, list) else []
  except Exception as exc:
    logger.debug("WSB sentiment fetch failed: %s", exc)
    return []


def ingest_sentiment_snapshot() -> dict:
  rows = fetch_wsb_mentions()
  db = SessionLocal()
  try:
    payload = {"items": rows[:50], "source": "tradestie_wsb"}
    key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    existing = (
      db.query(MarketSnapshot)
      .filter(MarketSnapshot.source == "wsb_sentiment", MarketSnapshot.snapshot_key == key)
      .first()
    )
    if existing is None:
      existing = MarketSnapshot(
        source="wsb_sentiment",
        snapshot_key=key,
        market="US",
        as_of=datetime.now(timezone.utc),
        payload=payload,
      )
      db.add(existing)
    else:
      existing.payload = payload
      existing.as_of = datetime.now(timezone.utc)
    db.commit()
    return {"stored": len(rows), "key": key}
  finally:
    db.close()


def mention_heat(ticker: str, db=None) -> dict:
  """Return heat 0..1 and veto hint from latest WSB snapshot."""
  own = db is None
  if own:
    db = SessionLocal()
  try:
    snap = (
      db.query(MarketSnapshot)
      .filter(MarketSnapshot.source == "wsb_sentiment")
      .order_by(MarketSnapshot.as_of.desc())
      .first()
    )
    if not snap or not snap.payload:
      return {"heat": 0.0, "veto": False, "comments": 0}
    items = snap.payload.get("items") or []
    t = ticker.upper().split(".")[0]
    max_c = max((int(i.get("no_of_comments") or 0) for i in items), default=1) or 1
    for i in items:
      if (i.get("ticker") or "").upper() == t:
        comments = int(i.get("no_of_comments") or 0)
        heat = min(1.0, comments / max_c)
        # Extreme meme heat alone is not a buy; mild veto if heat high but score bearish
        sent = (i.get("sentiment") or "").lower()
        veto = heat > 0.85 and sent == "bearish"
        return {"heat": heat, "veto": veto, "comments": comments, "sentiment": sent}
    return {"heat": 0.0, "veto": False, "comments": 0}
  finally:
    if own:
      db.close()
