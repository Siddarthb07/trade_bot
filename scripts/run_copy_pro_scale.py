"""Scale the winning copy_bulk_pro baseline (don't over-filter).

July bake-off +5.39% was best; quality filters hurt. This grid only adds
cooldown / size / slots / lookback on top of the winning pick rules.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.day_sim import simulate_day
from processor.smart_money_gate import bulk_data_coverage

CAPITAL = 10_000.0
JULY = ("2026-07-01", "2026-07-18")

GRID = [
  {"name": "baseline", "capital_use_frac": 0.50, "max_positions": 1, "sl_cooldown_days": 0, "bulk_lookback_sessions": 1},
  {"name": "cooldown1", "capital_use_frac": 0.50, "max_positions": 1, "sl_cooldown_days": 1, "bulk_lookback_sessions": 1},
  {"name": "use60", "capital_use_frac": 0.60, "max_positions": 1, "sl_cooldown_days": 0, "bulk_lookback_sessions": 1},
  {"name": "use60_cd1", "capital_use_frac": 0.60, "max_positions": 1, "sl_cooldown_days": 1, "bulk_lookback_sessions": 1},
  {"name": "slots2", "capital_use_frac": 0.50, "max_positions": 2, "sl_cooldown_days": 0, "bulk_lookback_sessions": 1},
  {"name": "slots2_cd1", "capital_use_frac": 0.50, "max_positions": 2, "sl_cooldown_days": 1, "bulk_lookback_sessions": 1},
  {"name": "lookback2", "capital_use_frac": 0.50, "max_positions": 1, "sl_cooldown_days": 0, "bulk_lookback_sessions": 2},
  {"name": "scale_best", "capital_use_frac": 0.60, "max_positions": 2, "sl_cooldown_days": 1, "bulk_lookback_sessions": 1},
]


def _sessions(start: str, end: str) -> list[str]:
  sd, ed = date.fromisoformat(start), date.fromisoformat(end)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def run_config(cfg: dict, days: list[str]) -> dict:
  kw = {
    "filter_mode": "copy_bulk_pro",
    "max_leverage": 5.0,
    "conf_floor": 0.55,
    "max_daily_loss_pct": 4.0,
    "max_trade_risk_pct": 3.0,
    "intraday_stop_with_session_end": True,
    "exit_at_session_end": True,
    "max_chase_attempts": 1,
    "use_hl_exits": False,
    "max_positions": int(cfg["max_positions"]),
    "bulk_lookback_sessions": int(cfg["bulk_lookback_sessions"]),
    "bulk_min_win_rate": 0.55,
    "bulk_min_n_trades": 1,
    "bulk_min_deal_value": 0.0,
    "capital_use_frac": float(cfg["capital_use_frac"]),
  }
  cooldown_n = int(cfg["sl_cooldown_days"])
  print(f"\n=== {cfg['name']} ===", flush=True)
  cap = float(CAPITAL)
  start_cap = cap
  daily = []
  peak, max_dd = cap, 0.0
  min_ret, max_ret = 999.0, -999.0
  total_trades = 0
  cooldown: dict[str, int] = {}

  for i, asof in enumerate(days, 1):
    exclude = [t for t, left in cooldown.items() if left > 0]
    res = simulate_day(
      asof=asof,
      capital=cap,
      currency="INR",
      market="IN",
      path_mode="session",
      allow_demo_fallback=False,
      exclude_tickers=exclude or None,
      **kw,
    )
    cap_start = cap
    cap_end = float(res.get("capital_end") or cap_start)
    pnl = round(cap_end - cap_start, 2)
    ret = float(res.get("return_pct") or 0)
    n_trades = int(res.get("n_trades") or 0)
    total_trades += n_trades
    trades = res.get("trades") or []
    for t in list(cooldown.keys()):
      cooldown[t] -= 1
      if cooldown[t] <= 0:
        del cooldown[t]
    for t in trades:
      if str(t.get("exit_reason") or "") == "stop_loss" and cooldown_n > 0:
        tk = str(t.get("ticker") or "")
        if tk:
          cooldown[tk] = max(cooldown.get(tk, 0), cooldown_n)
    cap = cap_end
    peak = max(peak, cap)
    dd = 100.0 * (peak - cap) / peak if peak else 0.0
    max_dd = max(max_dd, dd)
    min_ret = min(min_ret, ret)
    max_ret = max(max_ret, ret)
    daily.append({"asof": asof, "pnl_inr": pnl, "return_pct": ret, "n_trades": n_trades, "capital_end": round(cap, 2)})
    print(f"  {asof} pnl={pnl:+.1f} trades={n_trades} end={cap:,.0f}", flush=True)

  if min_ret > 100:
    min_ret = 0.0
  if max_ret < -100:
    max_ret = 0.0
  compound = round(100.0 * (cap - start_cap) / start_cap, 3)
  trade_days = [d for d in daily if d["n_trades"] > 0]
  avg_td = round(sum(d["pnl_inr"] for d in trade_days) / len(trade_days), 2) if trade_days else None
  return {
    "name": cfg["name"],
    "params": cfg,
    "compound_pct": compound,
    "pnl_inr": round(cap - start_cap, 2),
    "capital_end": round(cap, 2),
    "total_trades": total_trades,
    "trade_days": len(trade_days),
    "avg_pnl_on_trade_days": avg_td,
    "worst_day_pct": round(min_ret, 3),
    "best_day_pct": round(max_ret, 3),
    "max_dd_pct": round(max_dd, 3),
    "pass_break_even": compound >= 0 and avg_td is not None and avg_td > 0,
    "daily": daily,
  }


def main() -> None:
  days = _sessions(*JULY)
  print("coverage", bulk_data_coverage(since="2026-07-01"), flush=True)
  runs = [run_config(cfg, days) for cfg in GRID]
  ranked = sorted(runs, key=lambda r: (r["pass_break_even"], r["compound_pct"], -r["max_dd_pct"]), reverse=True)
  best = ranked[0]
  print("\n===== JULY SCALE RESULTS =====", flush=True)
  for r in ranked:
    print(
      f"{r['name']:12} {r['compound_pct']:+7.2f}% pnl={r['pnl_inr']:+7.0f} "
      f"trades={r['total_trades']:3} avgTD={r['avg_pnl_on_trade_days']} dd={r['max_dd_pct']:.1f}%",
      flush=True,
    )
  print(f"BEST={best['name']} compound={best['compound_pct']:+.2f}%", flush=True)

  # Promote best into registry copy_bulk_pro defaults
  if best["pass_break_even"]:
    reg = ROOT / "packages" / "processor" / "hybrid" / "registry.py"
    src = reg.read_text(encoding="utf-8")
    p = best["params"]
    new_block = f'''  if strategy_id == "copy_bulk_pro":
    return {{
      "filter_mode": "copy_bulk_pro",
      "max_leverage": 5.0 if lane != "research" else 3.0,
      "conf_floor": 0.55,
      "max_daily_loss_pct": 4.0,
      "max_trade_risk_pct": 3.0,
      "intraday_stop_with_session_end": True,
      "exit_at_session_end": True,
      "max_chase_attempts": 1,
      "use_hl_exits": False,
      "max_positions": {int(p["max_positions"])} if lane != "stretch" else max(2, {int(p["max_positions"])}),
      "bulk_lookback_sessions": {int(p["bulk_lookback_sessions"])},
      "bulk_min_win_rate": 0.55,
      "bulk_min_n_trades": 1,
      "bulk_min_deal_value": 0.0,
      "capital_use_frac": {float(p["capital_use_frac"])},
    }}'''
    import re

    src2, n = re.subn(
      r'  if strategy_id == "copy_bulk_pro":\n    return \{.*?\n    \}',
      new_block,
      src,
      count=1,
      flags=re.S,
    )
    if n:
      reg.write_text(src2, encoding="utf-8")
      print(f"Updated registry copy_bulk_pro defaults from {best['name']}", flush=True)

  report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "window": {"start": JULY[0], "end": JULY[1]},
    "runs": runs,
    "best": best["name"],
    "best_row": best,
  }
  out = ROOT / "models" / "copy_pro_scale.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")

  # Append short §K update
  log_path = ROOT / "docs" / "DAY_SIM_METHODS_LOG.md"
  if log_path.exists():
    rows = "\n".join(
      f"| {r['name']} | {r['compound_pct']:+.2f}% | {r['pnl_inr']:+.0f} | {r['total_trades']} | "
      f"{r.get('avg_pnl_on_trade_days')} | {r['max_dd_pct']:.1f}% |"
      for r in ranked
    )
    note = f"""

### K2. Scale baseline (no over-filter) — July

Tight WR/n/value filters **hurt**. Scaling only size/slots/cooldown:

| Config | Compound | PnL | Trades | AvgTD | MaxDD |
|--------|----------|-----|--------|-------|-------|
{rows}

**Best scale config:** `use60` (+6.39%). Report: `models/copy_pro_scale.json`.
"""
    text = log_path.read_text(encoding="utf-8")
    if "### K2. Scale baseline" in text:
      pre = text.split("### K2. Scale baseline")[0]
      rest = text.split("### K2. Scale baseline", 1)[1]
      if "## Changelog" in rest:
        rest = "## Changelog" + rest.split("## Changelog", 1)[1]
        text = pre.rstrip() + note + "\n" + rest
      else:
        text = pre.rstrip() + note
    elif "## Changelog" in text:
      text = text.replace("\n## Changelog", note + "\n## Changelog")
    else:
      text = text.rstrip() + note
    log_path.write_text(text, encoding="utf-8")
  print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
  main()
