"""Rolling paper/live expectancy metrics + Stage C weekly health freeze."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from core.models import Fill, Order, TradeRiskState


def _order_pnl_proxy(orders: list[Order], fills_by_order: dict) -> list[dict[str, Any]]:
  """Approximate closed round-trips: paired buy→sell by ticker chronologically (simple)."""
  trades: list[dict[str, Any]] = []
  open_buys: dict[str, list[Order]] = {}
  for o in sorted(orders, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc)):
    if o.status not in ("filled", "partial"):
      continue
    key = f"{o.market}:{o.ticker}"
    if o.side == "buy":
      open_buys.setdefault(key, []).append(o)
      continue
    if o.side == "sell" and open_buys.get(key):
      buy = open_buys[key].pop(0)
      bf = fills_by_order.get(buy.id)
      sf = fills_by_order.get(o.id)
      entry = float(bf.price) if bf else float(buy.limit_price or 0)
      exit_px = float(sf.price) if sf else float(o.limit_price or 0)
      qty = float(sf.qty if sf else o.qty or 0)
      fees = float((bf.fee if bf else 0) or 0) + float((sf.fee if sf else 0) or 0)
      pnl = (exit_px - entry) * qty - fees
      trades.append(
        {
          "ticker": o.ticker,
          "market": o.market,
          "pnl": pnl,
          "won": pnl > 0,
          "entry_at": buy.created_at.isoformat() if buy.created_at else None,
          "exit_at": o.created_at.isoformat() if o.created_at else None,
          "strategy_id": buy.strategy_id,
        }
      )
  return trades


def rolling_paper_metrics(db: Session, *, market: str | None = None, days: int = 30) -> dict[str, Any]:
  since = datetime.now(timezone.utc) - timedelta(days=days)
  q = db.query(Order).filter(Order.created_at >= since, Order.status.in_(["filled", "partial", "rejected"]))
  if market:
    q = q.filter(Order.market == market.upper())
  orders = q.order_by(Order.created_at.asc()).all()
  fills = db.query(Fill).order_by(desc(Fill.filled_at)).limit(5000).all()
  fills_by_order = {f.order_id: f for f in fills}
  closed = _order_pnl_proxy([o for o in orders if o.status in ("filled", "partial")], fills_by_order)
  n = len(closed)
  if n == 0:
    return {
      "days": days,
      "market": market or "ALL",
      "n_trades": 0,
      "hit_rate_pct": None,
      "expectancy": None,
      "total_pnl": 0.0,
      "max_dd": None,
      "pass_positive_expectancy": False,
      "note": "insufficient_closed_trades",
    }
  pnls = [t["pnl"] for t in closed]
  wins = sum(1 for t in closed if t["won"])
  total = sum(pnls)
  # Simple equity DD on cumulative pnl
  peak = 0.0
  equity = 0.0
  max_dd = 0.0
  for p in pnls:
    equity += p
    peak = max(peak, equity)
    dd = peak - equity
    max_dd = max(max_dd, dd)
  expectancy = total / n
  return {
    "days": days,
    "market": market or "ALL",
    "n_trades": n,
    "hit_rate_pct": round(100.0 * wins / n, 2),
    "expectancy": round(expectancy, 6),
    "total_pnl": round(total, 4),
    "max_dd": round(max_dd, 4),
    "wins": wins,
    "losses": n - wins,
    "pass_positive_expectancy": expectancy > 0,
    "disclaimer": "Not investment advice. Paper/live blotter metrics only.",
  }


def stage_c_health(db: Session) -> dict[str, Any]:
  """Stage C weekly freeze inputs: 30d + 90d expectancy and trade count."""
  m30 = rolling_paper_metrics(db, days=30)
  m90 = rolling_paper_metrics(db, days=90)
  # Freeze if we have enough trades and expectancy non-positive
  freeze = False
  reasons: list[str] = []
  if m30["n_trades"] >= 20 and not m30["pass_positive_expectancy"]:
    freeze = True
    reasons.append("30d_expectancy_non_positive")
  if m90["n_trades"] >= 50 and not m90["pass_positive_expectancy"]:
    freeze = True
    reasons.append("90d_expectancy_non_positive")
  return {
    "m30": m30,
    "m90": m90,
    "should_freeze": freeze,
    "reasons": reasons,
    "pass_stage_c_sketch": bool(
      m90["n_trades"] >= 50 and m90["pass_positive_expectancy"] and (m90.get("hit_rate_pct") or 0) > 0
    ),
  }


def apply_weekly_freeze_if_needed(db: Session) -> dict[str, Any]:
  from broker.risk import set_kill
  from processor.adaptive_edge import load_profiles, save_profiles

  health = stage_c_health(db)
  if not health["should_freeze"]:
    return {"status": "ok", "health": health}

  killed = set_kill(db, "ALL", kill=True)
  # Revoke ambition_pass on all profiles (fail closed until re-search)
  data = load_profiles()
  profiles = data.get("profiles") or {}
  revoked = []
  for t, p in profiles.items():
    if p.get("ambition_pass"):
      p["ambition_pass"] = False
      p["revoked_reason"] = "stage_c_weekly_freeze"
      revoked.append(t)
  if profiles:
    save_profiles(profiles)
  return {"status": "frozen", "killed": killed, "revoked": revoked, "health": health}
