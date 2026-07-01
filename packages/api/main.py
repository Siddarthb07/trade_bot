"""FastAPI application."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from core.config import get_settings
from core.db import get_db
from core.models import AlertLog, AlertPrefs, ForwardReturn, IngestionRun, InvestorStat, Signal, SignalScore
from core.queue import redis_conn, task_queue
from ingest.nse import ingest_nse_payloads
from notifier.dispatch import backfill_gate_passed
from notifier.waha import waha_healthy
from processor.explain import build_thesis
from processor.market_data import fetch_price_history
from processor.scoring import score_signal

settings = get_settings()
security = HTTPBasic()
app = FastAPI(title="Trade Bot API", version="0.1.0")

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)


def verify_basic(credentials: HTTPBasicCredentials = Depends(security)) -> None:
  if credentials.username != settings.api_username or credentials.password != settings.api_password:
    raise HTTPException(status_code=401, detail="Unauthorized")


def verify_basic_or_share(
  credentials: HTTPBasicCredentials = Depends(HTTPBasic(auto_error=False)),
  x_share_token: str | None = Header(default=None, alias="X-Share-Token"),
  k: str | None = Query(default=None),
) -> None:
  token = (x_share_token or k or "").strip()
  if settings.dashboard_share_token and token == settings.dashboard_share_token:
    return
  if credentials is None or credentials.username is None:
    raise HTTPException(status_code=401, detail="Unauthorized")
  verify_basic(credentials)


def verify_internal(x_api_key: str = Header(default="")) -> None:
  if x_api_key != settings.internal_api_key:
    raise HTTPException(status_code=401, detail="Invalid API key")


class AlertPrefsUpdate(BaseModel):
  min_tier: str | None = None
  quiet_hours_start: int | None = None
  quiet_hours_end: int | None = None
  market_in: bool | None = None
  market_us: bool | None = None


class NSEIngestPayload(BaseModel):
  signals: list[dict[str, Any]]


class PriceBatchItem(BaseModel):
  ticker: str
  market: str = "IN"


class PriceBatchRequest(BaseModel):
  items: list[PriceBatchItem]


def _latest_score(db: Session, signal_id: uuid.UUID) -> SignalScore | None:
  return (
    db.query(SignalScore)
    .filter(SignalScore.signal_id == signal_id)
    .order_by(desc(SignalScore.scored_at))
    .first()
  )


def _serialize_signal(db: Session, signal: Signal) -> dict[str, Any]:
  score = _latest_score(db, signal.id)
  raw = signal.raw_json or {}
  item = {
    "id": str(signal.id),
    "source": signal.source,
    "market": signal.market,
    "entity": signal.entity,
    "ticker": signal.ticker,
    "action": signal.action,
    "qty": signal.qty,
    "value": signal.value,
    "disclosed_at": signal.disclosed_at.isoformat(),
    "source_url": signal.source_url,
    "tier": score.tier if score else None,
    "historical_win_rate": score.historical_win_rate if score else None,
    "n_trades": score.n_trades if score else None,
    "scorer_version": score.scorer_version if score else None,
    "return_distribution": score.return_distribution if score else None,
    "calibrated_probability": (score.return_distribution or {}).get("calibrated_probability") if score else None,
  }
  if signal.source == "macro_theme" or raw.get("theme_slug"):
    item["theme"] = {
      "slug": raw.get("theme_slug"),
      "name": raw.get("theme_name"),
      "demand_driver": raw.get("demand_driver"),
      "company_name": raw.get("company_name"),
      "theme_heat": raw.get("theme_heat"),
      "alignment_score": raw.get("alignment_score"),
    }
  return item


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
  try:
    db.execute(func.now())
    db_ok = True
  except Exception:
    db_ok = False
  try:
    redis_ok = redis_conn.ping()
  except Exception:
    redis_ok = False
  return {
    "status": "ok" if db_ok and redis_ok else "degraded",
    "db": db_ok,
    "redis": redis_ok,
    "waha": waha_healthy(),
    "alerts_enabled": settings.alerts_enabled,
    "backfill_gate_passed": backfill_gate_passed(db),
    "queue_depth": len(task_queue),
  }


@app.get("/signals")
def list_signals(
  market: str | None = None,
  tier: str | None = None,
  source: str | None = None,
  limit: int = Query(default=50, le=200),
  offset: int = 0,
  db: Session = Depends(get_db),
  _: None = Depends(verify_basic_or_share),
) -> dict[str, Any]:
  query = db.query(Signal).order_by(desc(Signal.disclosed_at))
  if market:
    query = query.filter(Signal.market == market.upper())
  if source:
    query = query.filter(Signal.source == source)
  total = query.count()
  signals = query.offset(offset).limit(limit).all()
  items = []
  for signal in signals:
    item = _serialize_signal(db, signal)
    if tier and item.get("tier") != tier:
      continue
    items.append(item)
  return {"total": total, "items": items}


@app.get("/signals/top-picks")
def top_picks(
  market: str = "IN",
  limit: int = Query(default=5, le=10),
  db: Session = Depends(get_db),
  _: None = Depends(verify_basic_or_share),
) -> dict[str, Any]:
  from datetime import timedelta
  from zoneinfo import ZoneInfo

  ist = ZoneInfo("Asia/Kolkata")
  day_start = datetime.now(ist).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
  signals = (
    db.query(Signal)
    .filter(
      Signal.market == market.upper(),
      Signal.disclosed_at >= day_start - timedelta(hours=6),
    )
    .all()
  )
  ranked: list[tuple[float, dict]] = []
  for signal in signals:
    if signal.action.upper() not in ("BUY", "P", "A"):
      continue
    score = _latest_score(db, signal.id)
    if not score or not score.return_distribution:
      continue
    exp = score.return_distribution.get("expected_return_pct")
    if exp is None:
      continue
    ranked.append((float(exp), _serialize_signal(db, signal)))
  ranked.sort(key=lambda x: x[0], reverse=True)
  items = [item for _, item in ranked[:limit]]
  return {"items": items, "ranked_by": "expected_return_pct"}


@app.get("/themes")
def list_themes(
  market: str | None = None,
  db: Session = Depends(get_db),
  _: None = Depends(verify_basic_or_share),
) -> dict[str, Any]:
  from processor.macro_themes import THEMES, rank_all_picks
  from processor.market_data import compute_trend_features
  from core.tickers import normalize_ticker

  live = rank_all_picks(market=market, min_composite=0.0)
  by_theme: dict[str, list] = {}
  for pick in live:
    by_theme.setdefault(pick["theme_slug"], []).append(pick)

  themes_out = []
  for theme in THEMES:
    proxy = compute_trend_features(normalize_ticker(theme.proxy_ticker, "US"))
    proxy_3m = float(proxy.get("return_3m") or 0)
    heat = max(0.0, min(1.0, proxy_3m / 0.12))
    top = by_theme.get(theme.slug, [])[:5]
    themes_out.append({
      "slug": theme.slug,
      "name": theme.name,
      "demand_driver": theme.demand_driver,
      "world_context": theme.world_context,
      "proxy_ticker": theme.proxy_ticker,
      "theme_heat": round(heat, 3),
      "proxy_return_3m": proxy.get("return_3m"),
      "top_picks": top,
    })
  return {"themes": themes_out, "disclaimer": "Thematic research from public prices — not investment advice."}


@app.get("/themes/top-picks")
def theme_top_picks(
  market: str | None = None,
  limit: int = Query(default=10, le=20),
  db: Session = Depends(get_db),
  _: None = Depends(verify_basic_or_share),
) -> dict[str, Any]:
  from datetime import timedelta
  from zoneinfo import ZoneInfo

  ist = ZoneInfo("Asia/Kolkata")
  day_start = datetime.now(ist).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
  query = db.query(Signal).filter(
    Signal.source == "macro_theme",
    Signal.disclosed_at >= day_start - timedelta(hours=12),
  )
  if market:
    query = query.filter(Signal.market == market.upper())
  signals = query.all()
  ranked: list[tuple[float, dict]] = []
  for signal in signals:
    score = _latest_score(db, signal.id)
    if not score or not score.return_distribution:
      continue
    dist = score.return_distribution
    prob = dist.get("calibrated_probability")
    if prob is not None and float(prob) < settings.macro_themes_min_probability:
      continue
    composite = float(dist.get("composite_score") or dist.get("expected_return_pct") or 0)
    ranked.append((composite, _serialize_signal(db, signal)))
  ranked.sort(key=lambda x: x[0], reverse=True)
  return {"items": [item for _, item in ranked[:limit]], "ranked_by": "composite_score"}


@app.get("/themes/live-picks")
def live_theme_picks(
  market: str | None = None,
  limit: int = Query(default=20, le=50),
  no_bulk_only: bool = False,
  min_composite: float | None = None,
  db: Session = Depends(get_db),
  _: None = Depends(verify_basic_or_share),
) -> dict[str, Any]:
  """Always-computed demand picks (works even if daily ingest hasn't run)."""
  from datetime import timedelta

  from processor.macro_themes import rank_all_picks

  min_c = min_composite if min_composite is not None else settings.macro_themes_min_composite
  picks = rank_all_picks(market=market, min_composite=min_c)
  since = datetime.now(timezone.utc) - timedelta(days=30)

  seen: set[str] = set()
  items: list[dict[str, Any]] = []
  for pick in picks:
    key = f"{pick['market']}:{pick['ticker']}"
    if key in seen:
      continue
    seen.add(key)

    bulk_count = (
      db.query(Signal)
      .filter(
        Signal.ticker == pick["ticker"],
        Signal.market == pick["market"],
        Signal.source.in_(["nse_bulk", "nse_block", "sec_form4", "sec_13f"]),
        Signal.disclosed_at >= since,
      )
      .count()
    )
    has_bulk = bulk_count > 0
    if no_bulk_only and has_bulk:
      continue

    signal = (
      db.query(Signal)
      .filter(
        Signal.source == "macro_theme",
        Signal.ticker == pick["ticker"],
        Signal.market == pick["market"],
      )
      .order_by(desc(Signal.disclosed_at))
      .first()
    )

    items.append({
      "theme_slug": pick["theme_slug"],
      "theme_name": pick["theme_name"],
      "demand_driver": pick.get("demand_driver"),
      "ticker": pick["ticker"],
      "market": pick["market"],
      "company_name": pick["company_name"],
      "theme_heat": pick["theme_heat"],
      "alignment_score": pick["alignment_score"],
      "calibrated_probability": pick["calibrated_probability"],
      "expected_return_pct": pick["expected_return_pct"],
      "tier": pick["tier"],
      "composite_score": pick["composite_score"],
      "signal_id": str(signal.id) if signal else None,
      "has_bulk_deal": has_bulk,
      "sell_horizon_label": pick.get("sell_horizon_label"),
    })
    if len(items) >= limit:
      break

  return {"items": items, "ranked_by": "composite_score", "source": "live", "disclaimer": "Thematic research from public prices — not investment advice."}


@app.post("/market/price-history/batch")
def batch_price_history(
  payload: PriceBatchRequest,
  _: None = Depends(verify_basic_or_share),
) -> dict[str, Any]:
  from core.tickers import normalize_ticker
  from processor.market_data import compute_trend_features, fetch_price_history

  items: list[dict[str, Any]] = []
  for row in payload.items[:24]:
    norm = normalize_ticker(row.ticker, row.market.upper())
    prices = fetch_price_history(norm, days=180)
    trend = compute_trend_features(norm)
    items.append({
      "ticker": row.ticker.upper(),
      "market": row.market.upper(),
      "prices": prices,
      "trend": trend,
    })
  return {"items": items}


@app.get("/signals/{signal_id}")
def get_signal(
  signal_id: str,
  db: Session = Depends(get_db),
  _: None = Depends(verify_basic_or_share),
) -> dict[str, Any]:
  signal = db.query(Signal).filter(Signal.id == uuid.UUID(signal_id)).first()
  if not signal:
    raise HTTPException(status_code=404, detail="Signal not found")
  score = _latest_score(db, signal.id)
  returns = db.query(ForwardReturn).filter(ForwardReturn.signal_id == signal.id).all()
  peers = (
    db.query(Signal)
    .filter(
      Signal.ticker == signal.ticker,
      Signal.market == signal.market,
      Signal.id != signal.id,
    )
    .order_by(desc(Signal.disclosed_at))
    .limit(10)
    .all()
  )
  entity_stats = (
    db.query(InvestorStat)
    .filter(
      InvestorStat.entity_normalized == signal.entity_normalized,
      InvestorStat.market == signal.market,
    )
    .first()
  )
  bulk_investors = (
    db.query(Signal)
    .filter(
      Signal.ticker == signal.ticker,
      Signal.market == signal.market,
      Signal.source.in_(["nse_bulk", "nse_block"]),
    )
    .order_by(desc(Signal.disclosed_at))
    .limit(25)
    .all()
  )
  score_dict = {
    "tier": score.tier if score else None,
    "historical_win_rate": score.historical_win_rate if score else None,
    "n_trades": score.n_trades if score else None,
    "return_distribution": score.return_distribution if score else None,
    "scorer_version": score.scorer_version if score else None,
    "calibrated_probability": (score.return_distribution or {}).get("calibrated_probability") if score else None,
  }
  thesis = build_thesis(db, signal, score_dict)
  price_history = fetch_price_history(signal.ticker_normalized, days=180)
  return {
    "signal": _serialize_signal(db, signal),
    "returns": [
      {"window": r.window, "return_pct": r.return_pct, "price_source": r.price_source}
      for r in returns
    ],
    "entity_stats": {
      "win_rate": entity_stats.win_rate if entity_stats else None,
      "median_return": entity_stats.median_return if entity_stats else None,
      "n_trades": entity_stats.n_trades if entity_stats else 0,
    },
    "cluster_peers": [_serialize_signal(db, p) for p in peers],
    "bulk_investors": [
      {
        "entity": b.entity,
        "action": b.action,
        "value": b.value,
        "qty": b.qty,
        "disclosed_at": b.disclosed_at.isoformat(),
        "source": b.source,
      }
      for b in bulk_investors
    ],
    "price_history": price_history,
    "thesis": thesis,
    "score": score_dict,
  }


@app.get("/entities/{name}")
def get_entity(name: str, db: Session = Depends(get_db), _: None = Depends(verify_basic)) -> dict[str, Any]:
  normalized = name.upper().strip()
  stats = db.query(InvestorStat).filter(InvestorStat.entity_normalized == normalized).all()
  signals = (
    db.query(Signal)
    .filter(Signal.entity_normalized == normalized)
    .order_by(desc(Signal.disclosed_at))
    .limit(100)
    .all()
  )
  return {
    "entity": normalized,
    "stats": [
      {
        "market": s.market,
        "win_rate": s.win_rate,
        "median_return": s.median_return,
        "n_trades": s.n_trades,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
      }
      for s in stats
    ],
    "signals": [_serialize_signal(db, sig) for sig in signals],
  }


@app.get("/stats/calibration")
def calibration(db: Session = Depends(get_db), _: None = Depends(verify_basic)) -> dict[str, Any]:
  buckets: dict[str, dict[str, Any]] = {}
  scores = db.query(SignalScore).all()
  for score in scores:
    bucket = buckets.setdefault(score.tier, {"count": 0, "wins": 0, "returns": []})
    bucket["count"] += 1
    fr = (
      db.query(ForwardReturn)
      .filter(ForwardReturn.signal_id == score.signal_id, ForwardReturn.window == settings.win_window)
      .first()
    )
    if fr and fr.return_pct is not None:
      bucket["returns"].append(fr.return_pct)
      if fr.return_pct > settings.win_threshold_pct:
        bucket["wins"] += 1
  result = {}
  for tier, data in buckets.items():
    count = data["count"]
    returns = data["returns"]
    result[tier] = {
      "count": count,
      "realized_win_rate": (data["wins"] / len(returns)) if returns else None,
      "median_return": sorted(returns)[len(returns) // 2] if returns else None,
    }
  return {
    "scorer_version": "interim-v1",
    "disclaimer": "historical_win_rate is not calibrated probability until platt scorer ships",
    "buckets": result,
  }


@app.get("/ingestion/runs")
def ingestion_runs(limit: int = 20, db: Session = Depends(get_db), _: None = Depends(verify_basic)) -> dict[str, Any]:
  runs = db.query(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(limit).all()
  return {
    "items": [
      {
        "job_name": r.job_name,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "rows_in": r.rows_in,
        "rows_new": r.rows_new,
        "status": r.status,
        "error": r.error,
      }
      for r in runs
    ]
  }


@app.get("/settings/alerts")
def get_alert_settings(db: Session = Depends(get_db), _: None = Depends(verify_basic)) -> dict[str, Any]:
  prefs = db.query(AlertPrefs).filter(AlertPrefs.id == 1).first()
  return {
    "min_tier": prefs.min_tier if prefs else "MEDIUM",
    "quiet_hours_start": prefs.quiet_hours_start if prefs else 23,
    "quiet_hours_end": prefs.quiet_hours_end if prefs else 8,
    "market_in": prefs.market_in if prefs else True,
    "market_us": prefs.market_us if prefs else True,
    "alerts_enabled": settings.alerts_enabled,
    "dashboard_public_url": settings.dashboard_public_url,
  }


@app.patch("/settings/alerts")
def update_alert_settings(
  payload: AlertPrefsUpdate,
  db: Session = Depends(get_db),
  _: None = Depends(verify_basic),
) -> dict[str, Any]:
  prefs = db.query(AlertPrefs).filter(AlertPrefs.id == 1).first()
  if prefs is None:
    prefs = AlertPrefs()
    db.add(prefs)
  if payload.min_tier is not None:
    prefs.min_tier = payload.min_tier
  if payload.quiet_hours_start is not None:
    prefs.quiet_hours_start = payload.quiet_hours_start
  if payload.quiet_hours_end is not None:
    prefs.quiet_hours_end = payload.quiet_hours_end
  if payload.market_in is not None:
    prefs.market_in = payload.market_in
  if payload.market_us is not None:
    prefs.market_us = payload.market_us
  db.commit()
  return get_alert_settings(db)


@app.get("/system")
def system_status(db: Session = Depends(get_db), _: None = Depends(verify_basic)) -> dict[str, Any]:
  last_alert = db.query(AlertLog).order_by(desc(AlertLog.sent_at)).first()
  return {
    "signals_total": db.query(Signal).count(),
    "signals_today": db.query(Signal).filter(
      Signal.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    ).count(),
    "queue_depth": len(task_queue),
    "last_alert": {
      "channel": last_alert.channel,
      "status": last_alert.status,
      "sent_at": last_alert.sent_at.isoformat() if last_alert and last_alert.sent_at else None,
    }
    if last_alert
    else None,
    "health": health(db),
  }


@app.post("/internal/ingest/nse")
def internal_nse_ingest(payload: NSEIngestPayload, _: None = Depends(verify_internal)) -> dict[str, Any]:
  return ingest_nse_payloads(payload.signals)


@app.post("/internal/daily-picks")
def trigger_daily_picks(
  market: str = "IN",
  force: bool = False,
  _: None = Depends(verify_internal),
) -> dict[str, Any]:
  from notifier.daily_picks import send_daily_picks

  return send_daily_picks(market=market, force=force)


@app.post("/internal/ingest/macro")
def trigger_macro_ingest(
  market: str | None = None,
  _: None = Depends(verify_internal),
) -> dict[str, Any]:
  from ingest.macro import ingest_macro_themes

  return ingest_macro_themes(market=market or None)
