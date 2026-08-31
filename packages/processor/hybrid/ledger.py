"""Outcome ledger + chooser state persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "models" / "hybrid_outcome_ledger.jsonl"
STATE_PATH = ROOT / "models" / "hybrid_chooser_state.json"
TRADES_PATH = ROOT / "models" / "hybrid_trades.jsonl"


def _now() -> str:
  return datetime.now(timezone.utc).isoformat()


def load_chooser_state() -> dict[str, Any]:
  if not STATE_PATH.exists():
    return {"strategies": {}, "updated_at": None, "version": 1}
  try:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))
  except Exception:
    return {"strategies": {}, "updated_at": None, "version": 1}


def save_chooser_state(state: dict[str, Any]) -> None:
  STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
  state = dict(state)
  state["updated_at"] = _now()
  STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def append_outcome(row: dict[str, Any]) -> None:
  LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
  with LEDGER_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(row, default=str) + "\n")


def append_trade_record(row: dict[str, Any]) -> None:
  TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
  with TRADES_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(row, default=str) + "\n")


def load_recent_outcomes(limit: int = 100) -> list[dict[str, Any]]:
  if not LEDGER_PATH.exists():
    return []
  lines = LEDGER_PATH.read_text(encoding="utf-8").strip().splitlines()
  out: list[dict[str, Any]] = []
  for line in lines[-limit:]:
    try:
      out.append(json.loads(line))
    except json.JSONDecodeError:
      continue
  return list(reversed(out))


def load_trade_by_id(trade_id: str) -> dict[str, Any] | None:
  if not TRADES_PATH.exists():
    return None
  for line in TRADES_PATH.read_text(encoding="utf-8").strip().splitlines():
    try:
      row = json.loads(line)
    except json.JSONDecodeError:
      continue
    if str(row.get("trade_id") or "") == trade_id or str(row.get("id") or "") == trade_id:
      return row
  return None


def load_recent_trades(limit: int = 50) -> list[dict[str, Any]]:
  if not TRADES_PATH.exists():
    return []
  lines = TRADES_PATH.read_text(encoding="utf-8").strip().splitlines()
  out: list[dict[str, Any]] = []
  for line in lines[-limit:]:
    try:
      out.append(json.loads(line))
    except json.JSONDecodeError:
      continue
  return list(reversed(out))


def update_chooser_from_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
  """Recompute per-strategy expectancy from outcome rows."""
  state = load_chooser_state()
  buckets: dict[str, list[float]] = {}
  for o in outcomes:
    sid = str(o.get("strategy_id") or "unknown")
    pnl = float(o.get("pnl_pct") or o.get("session_return_pct") or 0)
    buckets.setdefault(sid, []).append(pnl)
  strategies = dict(state.get("strategies") or {})
  for sid, pnls in buckets.items():
    n = len(pnls)
    exp = sum(pnls) / n if n else 0.0
    hit = sum(1 for p in pnls if p > 0) / n if n else 0.0
    strategies[sid] = {
      "n": n,
      "expectancy": round(exp, 6),
      "hit_rate": round(hit, 4),
      "sum_pnl_pct": round(sum(pnls), 4),
    }
  state["strategies"] = strategies
  save_chooser_state(state)
  return state


def record_session_outcomes(
  *,
  asof: str,
  lane: str,
  strategy_id: str,
  regime: str,
  session_return_pct: float,
  trades: list[dict[str, Any]],
  chooser: dict[str, Any],
  sim_kwargs: dict[str, Any] | None = None,
  ticker_ranks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
  ranks = ticker_ranks or []
  rank_by_ticker = {str(r.get("ticker")): r for r in ranks}
  for pick_i, t in enumerate(trades, 1):
    ticker = str(t.get("ticker") or "")
    rank_row = rank_by_ticker.get(ticker) or {}
    why_parts = [
      f"strategy={strategy_id}",
      f"lane={lane}",
      f"regime={regime}",
      f"chooser={chooser.get('reason') or chooser.get('picked')}",
      f"conf={t.get('confidence')}",
      f"or_width={t.get('or_width_pct')}",
      f"signal={t.get('signal_reason')}",
      f"money_put={t.get('money_put')}",
      f"lev={t.get('leverage')}",
    ]
    if rank_row:
      why_parts.append(f"universe_rank={rank_row.get('rank')}")
      why_parts.append(f"score={rank_row.get('score')}")
    row = {
      "ts": _now(),
      "asof": asof,
      "lane": lane,
      "strategy_id": strategy_id,
      "regime": regime,
      "ticker": ticker,
      "pnl_pct": t.get("pnl_pct"),
      "pnl": t.get("pnl"),
      "exit_reason": t.get("exit_reason"),
      "leverage": t.get("leverage"),
      "confidence": t.get("confidence"),
      "or_width_pct": t.get("or_width_pct"),
      "money_put": t.get("money_put"),
      "money_returned": t.get("money_returned"),
      "trade_id": t.get("trade_id"),
      "session_return_pct": session_return_pct,
      "chooser_picked": chooser.get("picked"),
      "pick_order": pick_i,
    }
    append_outcome(row)
    append_trade_record(
      {
        "id": t.get("trade_id") or f"{asof}-{ticker}",
        "trade_id": t.get("trade_id"),
        "asof": asof,
        "lane": lane,
        "strategy_id": strategy_id,
        "regime": regime,
        "ticker": ticker,
        "entry_price": t.get("entry_price"),
        "exit_price": t.get("exit_price"),
        "entry_date": t.get("entry_date"),
        "exit_date": t.get("exit_date"),
        "qty": t.get("qty"),
        "pnl": t.get("pnl"),
        "pnl_pct": t.get("pnl_pct"),
        "fees": t.get("fees"),
        "exit_reason": t.get("exit_reason"),
        "leverage": t.get("leverage"),
        "confidence": t.get("confidence"),
        "or_width_pct": t.get("or_width_pct"),
        "or_width_bps": round(float(t.get("or_width_pct") or 0) * 1e4, 2),
        "vol_score": t.get("vol_score"),
        "tp_pct": t.get("tp_pct"),
        "sl_pct": t.get("sl_pct"),
        "slot_capital": t.get("slot_capital"),
        "target_notional": t.get("target_notional"),
        "money_put": t.get("money_put"),
        "money_returned": t.get("money_returned"),
        "signal_reason": t.get("signal_reason"),
        "guard_notes": t.get("guard_notes"),
        "pick_order": pick_i,
        "universe_rank": rank_row.get("rank"),
        "universe_score": rank_row.get("score"),
        "why_selected": " | ".join(str(p) for p in why_parts),
        "chooser": chooser,
        "sim_kwargs": sim_kwargs or {},
        "rank_row": rank_row,
        "markers": [
          {"side": "buy", "price": t.get("entry_price"), "ts": t.get("entry_date")},
          {"side": "sell", "price": t.get("exit_price"), "ts": t.get("exit_date")},
        ],
      }
    )
  return update_chooser_from_outcomes(load_recent_outcomes(limit=500))
