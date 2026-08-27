"""Strategy lab: classic signals + verification scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


@dataclass
class StrategySignal:
  strategy_id: str
  side: str  # buy | sell | flat
  confidence: float
  reason: str


def mom_cross(closes: list[float], *, fast: int = 10, slow: int = 30) -> StrategySignal:
  """Dual-MA cross events only — no continuous ma_state buys."""
  if len(closes) < slow + 1:
    return StrategySignal("mom_cross", "flat", 0.5, "insufficient_bars")
  arr = np.array(closes, dtype=float)
  fast_ma = arr[-fast:].mean()
  slow_ma = arr[-slow:].mean()
  prev_fast = arr[-fast - 1 : -1].mean()
  prev_slow = arr[-slow - 1 : -1].mean()
  if prev_fast <= prev_slow and fast_ma > slow_ma:
    conf = min(0.85, 0.55 + abs(fast_ma - slow_ma) / max(slow_ma, 1e-9))
    return StrategySignal("mom_cross", "buy", float(conf), "golden_cross")
  if prev_fast >= prev_slow and fast_ma < slow_ma:
    return StrategySignal("mom_cross", "sell", 0.6, "death_cross")
  return StrategySignal("mom_cross", "flat", 0.5, "no_cross")


def mean_rev_bb(closes: list[float], *, window: int = 20, num_std: float = 2.0) -> StrategySignal:
  if len(closes) < window:
    return StrategySignal("mean_rev_bb", "flat", 0.5, "insufficient_bars")
  arr = np.array(closes[-window:], dtype=float)
  mid = arr.mean()
  std = arr.std() or 1e-9
  px = arr[-1]
  z = (px - mid) / std
  if z <= -num_std:
    conf = min(0.8, 0.55 + abs(z) * 0.05)
    return StrategySignal("mean_rev_bb", "buy", float(conf), f"oversold_z={z:.2f}")
  if z >= num_std:
    return StrategySignal("mean_rev_bb", "sell", 0.6, f"overbought_z={z:.2f}")
  return StrategySignal("mean_rev_bb", "flat", 0.5, f"inside_band_z={z:.2f}")


def intraday_orb(
  closes: list[float],
  *,
  open_range_bars: int = 5,
  session_bars: list[float] | None = None,
) -> StrategySignal:
  """Opening-range breakout — requires same-session bars; refuses daily misuse."""
  bars = session_bars if session_bars is not None else None
  if bars is None:
    return StrategySignal("intraday_orb", "flat", 0.5, "needs_intraday_session_bars")
  if len(bars) < open_range_bars + 2:
    return StrategySignal("intraday_orb", "flat", 0.5, "insufficient_bars")
  opening = bars[:open_range_bars]
  hi, lo = max(opening), min(opening)
  px = bars[-1]
  width = hi - lo
  if width <= 0:
    return StrategySignal("intraday_orb", "flat", 0.5, "flat_range")
  if px > hi:
    conf = min(0.82, 0.58 + (px - hi) / width * 0.15)
    return StrategySignal("intraday_orb", "buy", float(conf), "breakout_above_or")
  if px < lo:
    return StrategySignal("intraday_orb", "sell", 0.58, "breakdown_below_or")
  return StrategySignal("intraday_orb", "flat", 0.5, "inside_or")


def session_or_breakout(
  bars: list[dict[str, Any]],
  *,
  open_range_bars: int = 5,
) -> dict[str, float | str | None]:
  """Opening-range metrics for vol-ranked session selection (no future peek)."""
  closes = [float(b["close"]) for b in bars if b.get("close") is not None]
  if len(closes) < open_range_bars + 2:
    return {"side": "flat", "or_width_pct": 0.0, "score": 0.0, "entry_i": 0, "entry_px": 0.0}
  opening = closes[:open_range_bars]
  hi, lo = max(opening), min(opening)
  mid = (hi + lo) / 2.0 if (hi + lo) else closes[open_range_bars]
  or_width_pct = (hi - lo) / mid if mid > 0 else 0.0
  entry_i = open_range_bars
  entry_px = closes[entry_i]
  side = "flat"
  conf = 0.5
  reason = "inside_or"
  for i in range(open_range_bars, len(closes)):
    px = closes[i]
    if px > hi:
      side = "buy"
      entry_i = i
      entry_px = px
      stretch = (px - hi) / max(hi - lo, 1e-9)
      conf = min(0.92, 0.62 + stretch * 0.25)
      reason = "breakout_above_or"
      break
    if px < lo:
      side = "sell"
      entry_i = i
      entry_px = px
      reason = "breakdown_below_or"
      break
  # Vol-momentum rank: wide range + strong breakout confidence
  score = or_width_pct * 100.0 + (conf - 0.5) if side == "buy" else 0.0
  return {
    "side": side,
    "or_width_pct": round(or_width_pct, 5),
    "score": round(score, 4),
    "entry_i": entry_i,
    "entry_px": entry_px,
    "confidence": conf,
    "reason": reason,
  }


def market_regime(closes: list[float]) -> str:
  if len(closes) < 50:
    return "unknown"
  arr = np.array(closes, dtype=float)
  ma50 = arr[-50:].mean()
  ret20 = (arr[-1] / arr[-21] - 1) if len(arr) >= 21 else 0.0
  vol = np.std(np.diff(arr[-21:]) / arr[-21:-1]) if len(arr) >= 22 else 0.0
  if ret20 < -0.08 or vol > 0.04:
    return "risk_off"
  if arr[-1] > ma50 and ret20 > 0.02:
    return "trend"
  return "chop"


def trend_follow(closes: list[float], *, fast: int = 10, slow: int = 30) -> StrategySignal:
  """Momentum cross only in trend regime."""
  if market_regime(closes) != "trend":
    return StrategySignal("trend_follow", "flat", 0.5, "not_trend_regime")
  s = mom_cross(closes, fast=fast, slow=slow)
  return StrategySignal("trend_follow", s.side, s.confidence, f"trend|{s.reason}")


def mean_rev_chop(closes: list[float], *, window: int = 20, num_std: float = 2.0) -> StrategySignal:
  """Bollinger mean-reversion only in chop regime."""
  if market_regime(closes) != "chop":
    return StrategySignal("mean_rev_chop", "flat", 0.5, "not_chop_regime")
  s = mean_rev_bb(closes, window=window, num_std=num_std)
  return StrategySignal("mean_rev_chop", s.side, s.confidence, f"chop|{s.reason}")


def verify_strategy_report(
  *,
  strategy_id: str,
  n_trades: int,
  expectancy: float,
  max_dd: float,
  oos_ok: bool,
  hit_rate_pct: float | None = None,
  min_trades: int = 30,
  ambition_hit_pct: float = 85.0,
) -> dict:
  """GO/NO-GO: expectancy primary; hit rate ambition secondary."""
  reasons = []
  if n_trades < min_trades:
    reasons.append("too_few_trades")
  if expectancy <= 0:
    reasons.append("non_positive_expectancy")
  if max_dd > 0.35:
    reasons.append("drawdown_too_high")
  if not oos_ok:
    reasons.append("oos_failed")
  status = "passed" if not reasons else "rejected"
  ambition_pass = (
    status == "passed"
    and hit_rate_pct is not None
    and hit_rate_pct >= ambition_hit_pct
  )
  return {
    "strategy_id": strategy_id,
    "status": status,
    "live_enabled_allowed": ambition_pass,
    "ambition_pass": ambition_pass,
    "reasons": reasons,
    "n_trades": n_trades,
    "expectancy": expectancy,
    "max_dd": max_dd,
    "hit_rate_pct": hit_rate_pct,
  }


def _signal_rets(
  closes: list[float],
  strategy_fn: Callable,
  *,
  start: int,
  end: int,
  cost_bps: float,
  min_conf: float = 0.0,
) -> list[float]:
  """Entry-only: trade when side is buy/sell (event strategies already flat most bars)."""
  rets: list[float] = []
  cost = cost_bps / 10000.0
  end = min(end, len(closes) - 1)
  for t in range(start, end):
    window = closes[: t + 1]
    sig = strategy_fn(window)
    if sig.side not in ("buy", "sell") or sig.confidence < min_conf:
      continue
    fwd = closes[t + 1] / closes[t] - 1.0
    if sig.side == "buy":
      rets.append(fwd - cost)
    else:
      rets.append(-fwd - cost)
  return rets


def _max_dd(rets: list[float]) -> float:
  eq = 1.0
  peak = 1.0
  max_dd = 0.0
  for r in rets:
    eq *= 1 + r
    peak = max(peak, eq)
    max_dd = max(max_dd, (peak - eq) / peak if peak else 0.0)
  return float(max_dd)


def walk_forward_backtest(
  closes: list[float],
  strategy_fn,
  *,
  train_bars: int = 120,
  test_bars: int = 40,
  cost_bps: float = 10.0,
  embargo_bars: int = 5,
  param_grid: list[dict] | None = None,
) -> dict:
  """Purged walk-forward: fit params on train only, evaluate on test with embargo."""
  sid = getattr(strategy_fn, "__name__", "strategy")
  if len(closes) < train_bars + test_bars + embargo_bars + 2:
    return verify_strategy_report(
      strategy_id=sid,
      n_trades=0,
      expectancy=0.0,
      max_dd=1.0,
      oos_ok=False,
      hit_rate_pct=None,
    )

  grid = param_grid or [{}]
  oos_rets: list[float] = []
  fold_exps: list[float] = []
  i = train_bars
  while i + test_bars + 1 < len(closes):
    train_start = max(40, i - train_bars)
    train_end = i
    test_start = i + embargo_bars
    test_end = min(len(closes) - 1, i + embargo_bars + test_bars)

    best_params = grid[0]
    best_exp = float("-inf")
    for params in grid:
      def _fn(window, _p=params):
        return strategy_fn(window, **_p) if _p else strategy_fn(window)

      train_rets = _signal_rets(closes, _fn, start=train_start, end=train_end, cost_bps=cost_bps)
      exp = sum(train_rets) / len(train_rets) if train_rets else -1.0
      if exp > best_exp:
        best_exp = exp
        best_params = params

    def _best_fn(window, _p=best_params):
      return strategy_fn(window, **_p) if _p else strategy_fn(window)

    fold_rets = _signal_rets(closes, _best_fn, start=test_start, end=test_end, cost_bps=cost_bps)
    if fold_rets:
      fold_exps.append(sum(fold_rets) / len(fold_rets))
      oos_rets.extend(fold_rets)
    i += test_bars

  if not oos_rets:
    return verify_strategy_report(
      strategy_id=sid,
      n_trades=0,
      expectancy=0.0,
      max_dd=1.0,
      oos_ok=False,
      hit_rate_pct=None,
    )

  exp = float(sum(oos_rets) / len(oos_rets))
  wins = sum(1 for r in oos_rets if r > 0)
  hit = 100.0 * wins / len(oos_rets)
  # OOS ok if majority of folds have positive expectancy
  pos_folds = sum(1 for e in fold_exps if e > 0)
  oos_ok = pos_folds >= max(1, (len(fold_exps) + 1) // 2) and exp > 0
  report = verify_strategy_report(
    strategy_id=sid,
    n_trades=len(oos_rets),
    expectancy=exp,
    max_dd=_max_dd(oos_rets),
    oos_ok=oos_ok,
    hit_rate_pct=round(hit, 2),
  )
  report["oos_expectancy"] = round(exp, 6)
  report["mean_return"] = round(exp, 6)
  report["fold_count"] = len(fold_exps)
  report["positive_folds"] = pos_folds
  return report
