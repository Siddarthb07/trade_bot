"""Per-market trade risk policy (kill, arm, caps, weekly loss, live dual-ACK)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import Order, TradeRiskState

settings = get_settings()

DEFAULTS = {
  "IN": {"max_notional_per_trade": 1000.0, "max_open_notional": 1000.0, "max_daily_loss": 500.0},
  "US": {"max_notional_per_trade": 10.0, "max_open_notional": 10.0, "max_daily_loss": 5.0},
}

WEEKLY_LOSS = {"IN": 1500.0, "US": 15.0}
WEEKLY_PATH = Path(__file__).resolve().parents[2] / "models" / "weekly_risk_state.json"
LIVE_PHRASE = "I_ACCEPT_MICRO_LIVE_RISK"


def _week_start(d: date | None = None) -> str:
  d = d or date.today()
  return (d - timedelta(days=d.weekday())).isoformat()


def _load_weekly() -> dict:
  if not WEEKLY_PATH.exists():
    return {}
  try:
    return json.loads(WEEKLY_PATH.read_text(encoding="utf-8"))
  except Exception:
    return {}


def _save_weekly(data: dict) -> None:
  WEEKLY_PATH.parent.mkdir(parents=True, exist_ok=True)
  WEEKLY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def weekly_realized(market: str) -> float:
  data = _load_weekly()
  m = market.upper()
  row = data.get(m) or {}
  if row.get("week_start") != _week_start():
    return 0.0
  return float(row.get("realized_pnl") or 0.0)


def record_weekly_pnl(market: str, pnl: float) -> float:
  data = _load_weekly()
  m = market.upper()
  ws = _week_start()
  row = data.get(m) or {}
  if row.get("week_start") != ws:
    row = {"week_start": ws, "realized_pnl": 0.0}
  row["realized_pnl"] = float(row.get("realized_pnl") or 0.0) + float(pnl)
  data[m] = row
  _save_weekly(data)
  return float(row["realized_pnl"])


def live_acks_ok(market: str) -> tuple[bool, str | None]:
  """Stage D: env ACK flag + confirm phrase both required for live."""
  m = market.upper()
  mode = settings.exec_mode_in if m == "IN" else settings.exec_mode_us
  if mode != "live":
    return True, None
  ack = settings.exec_live_ack_in if m == "IN" else settings.exec_live_ack_us
  if not ack:
    return False, "live_ack_missing"
  phrase = (settings.exec_live_confirm_phrase or "").strip()
  if phrase != LIVE_PHRASE:
    return False, "live_confirm_phrase_missing"
  return True, None


def ensure_risk_state(db: Session, market: str) -> TradeRiskState:
  m = market.upper()
  row = db.query(TradeRiskState).filter(TradeRiskState.market == m).first()
  if row:
    return row
  d = DEFAULTS.get(m, DEFAULTS["US"])
  row = TradeRiskState(
    market=m,
    max_notional_per_trade=d["max_notional_per_trade"],
    max_open_notional=d["max_open_notional"],
    max_daily_loss=d["max_daily_loss"],
    kill_switch=True,
    exec_mode="paper",
    session_armed=False,
  )
  db.add(row)
  db.commit()
  db.refresh(row)
  return row


def _reset_daily_if_needed(row: TradeRiskState) -> None:
  today = date.today()
  if row.daily_pnl_date != today:
    row.daily_pnl_date = today
    row.daily_realized_pnl = 0.0


def authorize(
  db: Session,
  *,
  market: str,
  notional: float,
  book: str = "swing",
) -> tuple[bool, str | None, TradeRiskState]:
  row = ensure_risk_state(db, market)
  _reset_daily_if_needed(row)

  mode = settings.exec_mode_in if market.upper() == "IN" else settings.exec_mode_us
  if mode == "off":
    return False, "exec_mode_off", row
  if mode == "live":
    ok, why = live_acks_ok(market)
    if not ok:
      return False, why, row

  if row.kill_switch:
    return False, "kill_switch", row
  if not row.session_armed:
    return False, "session_not_armed", row
  if notional > row.max_notional_per_trade + 1e-9:
    return False, "over_per_trade_cap", row
  if row.daily_realized_pnl <= -abs(row.max_daily_loss):
    return False, "max_daily_loss", row

  weekly = weekly_realized(market)
  max_weekly = WEEKLY_LOSS.get(market.upper(), WEEKLY_LOSS["US"])
  # Scale weekly with ladder stage roughly
  max_weekly = max_weekly * (2 ** max(0, int(row.ladder_stage or 0)))
  if weekly <= -abs(max_weekly):
    return False, "max_weekly_loss", row

  open_orders = (
    db.query(Order)
    .filter(Order.market == market.upper(), Order.status.in_(["submitted", "filled", "partial"]))
    .all()
  )
  open_buy = [o for o in open_orders if o.side == "buy" and o.status in ("submitted", "filled", "partial")]
  open_notional = sum(float(o.sized_notional or o.notional or 0) for o in open_buy)
  open_tickers = {o.ticker for o in open_buy}
  if len(open_tickers) >= row.max_open_positions and book == "swing":
    pass
  if open_notional + notional > row.max_open_notional + 1e-9:
    return False, "over_open_notional", row

  today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  trades_today = (
    db.query(Order)
    .filter(Order.market == market.upper(), Order.created_at >= today_start, Order.status != "rejected")
    .count()
  )
  if trades_today >= row.max_trades_per_day:
    return False, "max_trades_per_day", row

  return True, None, row


def set_kill(db: Session, market: str | None, *, kill: bool) -> list[str]:
  markets = [market.upper()] if market and market.upper() != "ALL" else ["IN", "US"]
  touched = []
  for m in markets:
    row = ensure_risk_state(db, m)
    row.kill_switch = kill
    row.updated_at = datetime.now(timezone.utc)
    if kill:
      row.session_armed = False
    touched.append(m)
  db.commit()
  return touched


def arm_sessions(db: Session, *, markets: list[str] | None = None) -> list[str]:
  ms = markets or ["IN", "US"]
  out = []
  for m in ms:
    row = ensure_risk_state(db, m.upper())
    row.session_armed = True
    row.kill_switch = False
    row.updated_at = datetime.now(timezone.utc)
    out.append(m.upper())
  db.commit()
  return out


def end_session_disarm(db: Session, market: str) -> None:
  """Stage D: kill default on after session until manual re-arm."""
  row = ensure_risk_state(db, market)
  row.session_armed = False
  row.kill_switch = True
  row.updated_at = datetime.now(timezone.utc)
  db.commit()
