"""Multi-day session sim sweep: filter/frequency/TP-SL toward a daily return target.

Sim-only research — not live eligibility. Default target: 10% daily (ambition marker).
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.day_sim import simulate_day

TARGET_RETURN_PCT = 10.0
CAPITAL = 10_000.0
MARKET = "IN"
N_DAYS = 12  # recent trading sessions


def _trading_days(end: date, n: int) -> list[str]:
  out: list[str] = []
  d = end
  while len(out) < n:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d -= timedelta(days=1)
  return list(reversed(out))


# Leverage grid (sim-only margin)
LEVERAGE_CONFIGS: list[dict] = [
  {"name": "baseline_1x_scalp", "filter_mode": "orb_only", "conf_floor": 0.52, "max_positions": 3,
   "tp_override": 0.015, "sl_override": 0.007, "horizon_override": 4, "max_leverage": 1.0},
  {"name": "baseline_1x_top1", "filter_mode": "orb_only", "conf_floor": 0.55, "max_positions": 1,
   "tp_override": 0.015, "sl_override": 0.007, "horizon_override": 4, "max_leverage": 1.0},
  {"name": "lev5x_scalp_3pos", "filter_mode": "orb_only", "conf_floor": 0.52, "max_positions": 3,
   "tp_override": 0.015, "sl_override": 0.007, "horizon_override": 4, "max_leverage": 5.0},
  {"name": "lev10x_top1", "filter_mode": "orb_only", "conf_floor": 0.52, "max_positions": 1,
   "tp_override": 0.015, "sl_override": 0.007, "horizon_override": 4, "max_leverage": 10.0,
   "leverage_conf_full": 0.75},
  {"name": "lev15x_top1", "filter_mode": "orb_only", "conf_floor": 0.55, "max_positions": 1,
   "tp_override": 0.015, "sl_override": 0.007, "horizon_override": 4, "max_leverage": 15.0,
   "leverage_conf_full": 0.78},
  {"name": "lev20x_top1", "filter_mode": "orb_only", "conf_floor": 0.55, "max_positions": 1,
   "tp_override": 0.02, "sl_override": 0.008, "horizon_override": 5, "max_leverage": 20.0,
   "leverage_conf_full": 0.80},
  {"name": "lev25x_top1_high", "filter_mode": "orb_only", "conf_floor": 0.58, "max_positions": 1,
   "high_conf_floor": 0.68, "tp_override": 0.02, "sl_override": 0.008, "horizon_override": 5,
   "max_leverage": 25.0, "leverage_conf_full": 0.78},
  {"name": "lev30x_extreme_top1", "filter_mode": "orb_only", "conf_floor": 0.60, "max_positions": 1,
   "high_conf_floor": 0.70, "tp_override": 0.025, "sl_override": 0.01, "horizon_override": 6,
   "max_leverage": 30.0, "leverage_conf_full": 0.75},
  {"name": "lev20x_top2", "filter_mode": "orb_only", "conf_floor": 0.52, "max_positions": 2,
   "tp_override": 0.015, "sl_override": 0.007, "horizon_override": 4, "max_leverage": 20.0},
  {"name": "lev15x_high_conf", "filter_mode": "relaxed", "conf_floor": 0.58, "max_positions": 1,
   "high_conf_floor": 0.72, "tp_override": 0.018, "sl_override": 0.008, "horizon_override": 5,
   "max_leverage": 15.0, "leverage_conf_full": 0.80},
  {"name": "lev25x_aggressive_top1", "filter_mode": "aggressive", "conf_floor": 0.50, "max_positions": 1,
   "tp_override": 0.02, "sl_override": 0.008, "horizon_override": 5, "max_leverage": 25.0,
   "leverage_conf_full": 0.72},
  {"name": "lev10x_wide_tp_top1", "filter_mode": "orb_only", "conf_floor": 0.55, "max_positions": 1,
   "tp_override": 0.03, "sl_override": 0.012, "horizon_override": 8, "max_leverage": 10.0},
  {"name": "lev20x_wide_tp_top1", "filter_mode": "orb_only", "conf_floor": 0.55, "max_positions": 1,
   "tp_override": 0.04, "sl_override": 0.015, "horizon_override": 10, "max_leverage": 20.0},
  {"name": "lev30x_allin_best", "filter_mode": "orb_only", "conf_floor": 0.50, "max_positions": 1,
   "tp_override": 0.035, "sl_override": 0.012, "horizon_override": 8, "max_leverage": 30.0,
   "leverage_conf_full": 0.70},
]

# Filter grid (1x, no target_return) — re-runnable; archived in day_sim_experiment_report.json
FILTER_CONFIGS: list[dict] = [
  {"name": "strict_baseline", "filter_mode": "strict", "conf_floor": 0.70, "max_positions": 3, "max_leverage": 1.0},
  {"name": "relaxed_default", "filter_mode": "relaxed", "conf_floor": 0.58, "max_positions": 5, "max_leverage": 1.0},
  {"name": "orb_only_low", "filter_mode": "orb_only", "conf_floor": 0.50, "max_positions": 6, "max_leverage": 1.0},
  {"name": "orb_scalp_15pct", "filter_mode": "orb_only", "conf_floor": 0.52, "max_positions": 6,
   "tp_override": 0.015, "sl_override": 0.007, "horizon_override": 4, "max_leverage": 1.0},
  {"name": "relaxed_scalp", "filter_mode": "relaxed", "conf_floor": 0.52, "max_positions": 6,
   "tp_override": 0.012, "sl_override": 0.006, "horizon_override": 4, "max_leverage": 1.0},
  {"name": "aggressive_default", "filter_mode": "aggressive", "conf_floor": 0.48, "max_positions": 6, "max_leverage": 1.0},
  {"name": "relaxed_trend_only", "filter_mode": "relaxed", "conf_floor": 0.55, "max_positions": 5,
   "regime_allow": ["trend_up"], "max_leverage": 1.0},
  {"name": "orb_trend_only", "filter_mode": "orb_only", "conf_floor": 0.52, "max_positions": 5,
   "tp_override": 0.015, "sl_override": 0.007, "horizon_override": 5,
   "regime_allow": ["trend_up"], "max_leverage": 1.0},
]

CONFIGS = LEVERAGE_CONFIGS


def _run_config(name: str, days: list[str], kwargs: dict) -> dict:
  daily_returns: list[float] = []
  daily_trades: list[int] = []
  daily_hits: list[float] = []
  day_details: list[dict] = []
  total_pnl = 0.0
  wins = losses = 0

  for asof in days:
    res = simulate_day(
      asof=asof,
      capital=CAPITAL,
      currency="INR",
      market=MARKET,
      path_mode="session",
      allow_demo_fallback=False,
      **kwargs,
    )
    ret = float(res.get("return_pct") or 0)
    n = int(res.get("n_trades") or 0)
    daily_returns.append(ret)
    daily_trades.append(n)
    total_pnl += float(res.get("realized_pnl") or 0)
    ps = res.get("pnl_statement") or {}
    hr = ps.get("hit_rate_pct")
    if hr is not None and n > 0:
      daily_hits.append(float(hr))
      wins += int(ps.get("wins") or 0)
      losses += int(ps.get("losses") or 0)
    day_details.append(
      {
        "asof": asof,
        "return_pct": ret,
        "n_trades": n,
        "pnl": res.get("realized_pnl"),
        "hit_rate_pct": hr,
      }
    )

  n_days = len(days)
  avg_ret = sum(daily_returns) / n_days if n_days else 0
  max_ret = max(daily_returns) if daily_returns else 0
  min_ret = min(daily_returns) if daily_returns else 0
  days_ge_target = sum(1 for r in daily_returns if r >= TARGET_RETURN_PCT)
  days_positive = sum(1 for r in daily_returns if r > 0)
  avg_trades = sum(daily_trades) / n_days if n_days else 0
  pooled_hit = round(100.0 * wins / (wins + losses), 2) if (wins + losses) else None
  avg_hit = round(sum(daily_hits) / len(daily_hits), 2) if daily_hits else None
  # Score: distance from target + reward frequency + penalize heavy losses
  gap = abs(TARGET_RETURN_PCT - avg_ret)
  score = avg_ret - gap * 0.5 + (days_ge_target * 2.0) + (days_positive * 0.3) - max(0, -min_ret) * 0.2

  return {
    "name": name,
    "params": kwargs,
    "max_leverage": kwargs.get("max_leverage", 1.0),
    "n_days": n_days,
    "avg_return_pct": round(avg_ret, 3),
    "max_return_pct": round(max_ret, 3),
    "min_return_pct": round(min_ret, 3),
    "total_pnl_inr": round(total_pnl, 2),
    "avg_trades_per_day": round(avg_trades, 2),
    "days_at_or_above_target": days_ge_target,
    "days_positive": days_positive,
    "pooled_hit_rate_pct": pooled_hit,
    "avg_daily_hit_rate_pct": avg_hit,
    "target_return_pct": TARGET_RETURN_PCT,
    "score_vs_target": round(score, 3),
    "days": day_details,
  }


def main() -> None:
  import argparse

  parser = argparse.ArgumentParser(description="Day-sim experiment sweep")
  parser.add_argument(
    "--grid",
    choices=("leverage", "filter", "all"),
    default="leverage",
    help="leverage=margin grid (default); filter=1x filter modes; all=both",
  )
  args = parser.parse_args()
  if args.grid == "filter":
    configs = FILTER_CONFIGS
    out_name = "day_sim_experiment_report.json"
  elif args.grid == "all":
    configs = FILTER_CONFIGS + LEVERAGE_CONFIGS
    out_name = "day_sim_combined_experiment_report.json"
  else:
    configs = LEVERAGE_CONFIGS
    out_name = "day_sim_leverage_experiment_report.json"

  ist = ZoneInfo("Asia/Kolkata")
  end = datetime.now(ist).date()
  while end.weekday() >= 5:
    end -= timedelta(days=1)
  days = _trading_days(end, N_DAYS)

  print(f"Day-sim experiment sweep | {MARKET} | INR {CAPITAL:,.0f} | target {TARGET_RETURN_PCT}%/day")
  print(f"Sessions: {days[0]} -> {days[-1]} ({len(days)} days)")
  print(f"Configs: {len(configs)} (grid={args.grid})")
  print()

  results: list[dict] = []
  for i, cfg in enumerate(configs, 1):
    name = cfg["name"]
    kwargs = {k: v for k, v in cfg.items() if k != "name"}
    print(f"[{i}/{len(configs)}] {name} ...", flush=True)
    results.append(_run_config(name, days, kwargs))

  results.sort(key=lambda r: r["score_vs_target"], reverse=True)

  report = {
    "generated_at": datetime.now(ist).isoformat(),
    "target_return_pct": TARGET_RETURN_PCT,
    "capital_inr": CAPITAL,
    "market": MARKET,
    "sessions": days,
    "ranked": results,
    "best": results[0] if results else None,
    "disclaimer": "Sim-only; session ORB + modeled costs; not investment advice.",
  }

  out_path = ROOT / "models" / out_name
  out_path.parent.mkdir(parents=True, exist_ok=True)
  out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

  print()
  print("=" * 72)
  print(f"TOP 5 (target {TARGET_RETURN_PCT}% daily) - ranked by score_vs_target")
  print("=" * 72)
  hdr = f"{'config':<24} {'lev':>4} {'avg%':>7} {'max%':>7} {'min%':>7} {'tr/d':>5} {'hit%':>6} {'>=10%':>6} {'score':>7}"
  print(hdr)
  print("-" * len(hdr))
  for r in results[:5]:
    hit = r["pooled_hit_rate_pct"]
    hit_s = f"{hit:.1f}" if hit is not None else "n/a"
    print(
      f"{r['name']:<24} {r.get('max_leverage', 1):>4.0f} {r['avg_return_pct']:>7.3f} {r['max_return_pct']:>7.3f} "
      f"{r['min_return_pct']:>7.3f} {r['avg_trades_per_day']:>5.1f} {hit_s:>6} "
      f"{r['days_at_or_above_target']:>6} {r['score_vs_target']:>7.2f}"
    )

  best = results[0]
  print()
  print(f"Best config: {best['name']}")
  print(f"  avg return {best['avg_return_pct']}% | best day {best['max_return_pct']}% | worst {best['min_return_pct']}%")
  print(f"  {best['days_at_or_above_target']}/{best['n_days']} days hit >={TARGET_RETURN_PCT}% target")
  print(f"  total PnL INR {best['total_pnl_inr']:,.2f} over {best['n_days']} sessions")
  print(f"Report: {out_path}")


if __name__ == "__main__":
  main()
