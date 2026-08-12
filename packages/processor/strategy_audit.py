"""Per-ticker / per-regime strategy audit → playbook selection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from processor.strategies import (
  mean_rev_bb,
  mean_rev_chop,
  mom_cross,
  trend_follow,
  walk_forward_backtest,
)

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK_PATH = ROOT / "models" / "ticker_playbooks.json"
LADDER_PATH = ROOT / "models" / "hit_rate_ladder.json"

# Strategies audited on daily bars (ORB excluded — needs intraday session bars)
CANDIDATES: dict[str, Callable] = {
  "mom_cross": mom_cross,
  "mean_rev_bb": mean_rev_bb,
  "trend_follow": trend_follow,
  "mean_rev_chop": mean_rev_chop,
}

# adaptive_edge is primary live router (see ensemble / adaptive_edge.py) — not in classic audit grid


PARAM_GRIDS: dict[str, list[dict]] = {
  "mom_cross": [{}, {"fast": 8, "slow": 25}, {"fast": 12, "slow": 40}],
  "mean_rev_bb": [{}, {"window": 15, "num_std": 2.0}, {"window": 25, "num_std": 2.5}],
  "trend_follow": [{}, {"fast": 8, "slow": 25}],
  "mean_rev_chop": [{}, {"window": 20, "num_std": 2.0}, {"window": 15, "num_std": 2.5}],
}

AMBITION_HIT = 85.0
SOFT_HIT = 50.0  # paper/study playbooks; live still needs ambition_pass (≥85%)


def audit_ticker(closes: list[float], ticker: str) -> dict:
  """Walk-forward each candidate; pick best soft-pass / ambition_pass playbook."""
  reports: dict[str, dict] = {}
  for sid, fn in CANDIDATES.items():
    reports[sid] = walk_forward_backtest(
      closes,
      fn,
      train_bars=120,
      test_bars=40,
      cost_bps=10.0,
      embargo_bars=5,
      param_grid=PARAM_GRIDS.get(sid),
    )

  soft: list[tuple[str, dict]] = []
  ambition: list[tuple[str, dict]] = []
  for sid, rep in reports.items():
    hit = rep.get("hit_rate_pct")
    exp = float(rep.get("expectancy") or 0)
    if rep.get("status") == "passed" and hit is not None and hit >= SOFT_HIT and exp > 0:
      soft.append((sid, rep))
    if rep.get("ambition_pass"):
      ambition.append((sid, rep))

  soft.sort(key=lambda x: float(x[1].get("expectancy") or 0), reverse=True)
  ambition.sort(key=lambda x: float(x[1].get("expectancy") or 0), reverse=True)

  best = ambition[0] if ambition else (soft[0] if soft else None)
  second = None
  pool = ambition if ambition else soft
  if len(pool) >= 2:
    second = pool[1]

  playbook = {
    "ticker": ticker,
    "status": "passed" if best else "rejected",
    "ambition_pass": bool(ambition),
    "strategy_id": best[0] if best else None,
    "secondary_strategy_id": second[0] if second else None,
    "oos_hit_rate": best[1].get("hit_rate_pct") if best else None,
    "oos_expectancy": best[1].get("expectancy") if best else None,
    "n_trades": best[1].get("n_trades") if best else 0,
    "max_dd": best[1].get("max_dd") if best else None,
    "candidates": reports,
  }
  return playbook


def build_playbooks(series: dict[str, list[float]]) -> dict:
  """series: ticker -> closes."""
  playbooks = {}
  for ticker, closes in series.items():
    if len(closes) < 200:
      playbooks[ticker] = {"ticker": ticker, "status": "rejected", "reason": "insufficient_bars"}
      continue
    playbooks[ticker] = audit_ticker(closes, ticker)

  out = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "ambition_hit_pct": AMBITION_HIT,
    "soft_hit_pct": SOFT_HIT,
    "playbooks": playbooks,
    "disclaimer": "OOS walk-forward on daily bars; not live fills; not investment advice.",
  }
  PLAYBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
  PLAYBOOK_PATH.write_text(json.dumps(out, indent=2))
  return out


def load_playbooks() -> dict:
  if not PLAYBOOK_PATH.exists():
    return {"playbooks": {}}
  try:
    return json.loads(PLAYBOOK_PATH.read_text())
  except Exception:
    return {"playbooks": {}}


def load_playbook(ticker: str) -> dict | None:
  data = load_playbooks()
  pb = (data.get("playbooks") or {}).get(ticker)
  if not pb:
    # Try bare symbol without exchange suffix
    bare = ticker.split(".")[0]
    for k, v in (data.get("playbooks") or {}).items():
      if k.split(".")[0] == bare:
        return v
  return pb


def hit_rate_ladder(
  closes: list[float],
  strategy_fn: Callable,
  *,
  thresholds: list[float] | None = None,
  warm: int = 60,
  cost_bps: float = 10.0,
) -> list[dict]:
  """Selectivity curve: hit rate vs min confidence."""
  thresholds = thresholds or [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
  cost = cost_bps / 10000.0
  rows = []
  for thr in thresholds:
    rets: list[float] = []
    for i in range(warm, len(closes) - 1):
      sig = strategy_fn(closes[: i + 1])
      if sig.side not in ("buy", "sell") or sig.confidence < thr:
        continue
      fwd = closes[i + 1] / closes[i] - 1.0
      pnl = (fwd - cost) if sig.side == "buy" else (-fwd - cost)
      rets.append(pnl)
    if not rets:
      rows.append({"min_conf": thr, "n_trades": 0, "hit_rate_pct": None, "expectancy": None})
      continue
    wins = sum(1 for r in rets if r > 0)
    rows.append(
      {
        "min_conf": thr,
        "n_trades": len(rets),
        "hit_rate_pct": round(100.0 * wins / len(rets), 2),
        "expectancy": round(sum(rets) / len(rets), 6),
      }
    )
  return rows
