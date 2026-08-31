"""Push copy_bulk_pro: quality filters + SL cooldown + capital_use / positions grid.

Doubles down on the break-even bake-off winner. Writes models/copy_pro_push.json
and appends §K to DAY_SIM_METHODS_LOG.md.
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
WINDOWS = {
  "july": ("2026-07-01", "2026-07-18"),
  "august": ("2026-08-01", "2026-08-28"),
}

# Baseline (bake-off winner) vs hardened / sized variants
GRID = [
  {
    "name": "baseline_bakeoff",
    "capital_use_frac": 0.50,
    "max_positions": 1,
    "bulk_min_n_trades": 1,
    "bulk_min_deal_value": 0.0,
    "bulk_min_win_rate": 0.55,
    "sl_cooldown_days": 0,
  },
  {
    "name": "quality_v1",
    "capital_use_frac": 0.50,
    "max_positions": 1,
    "bulk_min_n_trades": 2,
    "bulk_min_deal_value": 25_000_000.0,
    "bulk_min_win_rate": 0.55,
    "sl_cooldown_days": 1,
  },
  {
    "name": "quality_size60",
    "capital_use_frac": 0.60,
    "max_positions": 1,
    "bulk_min_n_trades": 2,
    "bulk_min_deal_value": 25_000_000.0,
    "bulk_min_win_rate": 0.55,
    "sl_cooldown_days": 1,
  },
  {
    "name": "quality_2slot",
    "capital_use_frac": 0.50,
    "max_positions": 2,
    "bulk_min_n_trades": 2,
    "bulk_min_deal_value": 25_000_000.0,
    "bulk_min_win_rate": 0.55,
    "sl_cooldown_days": 1,
  },
  {
    "name": "quality_wr60",
    "capital_use_frac": 0.55,
    "max_positions": 1,
    "bulk_min_n_trades": 2,
    "bulk_min_deal_value": 25_000_000.0,
    "bulk_min_win_rate": 0.60,
    "sl_cooldown_days": 1,
  },
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


def _base_kw(cfg: dict) -> dict:
  return {
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
    "bulk_lookback_sessions": 1,
    "bulk_min_win_rate": float(cfg["bulk_min_win_rate"]),
    "bulk_min_n_trades": int(cfg["bulk_min_n_trades"]),
    "bulk_min_deal_value": float(cfg["bulk_min_deal_value"]),
    "capital_use_frac": float(cfg["capital_use_frac"]),
  }


def run_config(cfg: dict, days: list[str], *, window: str) -> dict:
  kw = _base_kw(cfg)
  cooldown_n = int(cfg.get("sl_cooldown_days") or 0)
  print(
    f"\n=== {cfg['name']} | {window} | use={cfg['capital_use_frac']:.0%} "
    f"pos={cfg['max_positions']} cooldown={cooldown_n} ===",
    flush=True,
  )
  cap = float(CAPITAL)
  start_cap = cap
  daily: list[dict] = []
  peak, max_dd = cap, 0.0
  min_ret, max_ret = 999.0, -999.0
  total_trades = 0
  # ticker -> remaining cooldown sessions after SL
  cooldown: dict[str, int] = {}

  for i, asof in enumerate(days, 1):
    exclude = [t for t, left in cooldown.items() if left > 0]
    print(f"  [{i}/{len(days)}] {asof} exclude={exclude or '-'} ...", flush=True)
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
    # Age existing cooldowns first, then arm fresh SL blocks for next session(s).
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
    daily.append(
      {
        "asof": asof,
        "capital_start": round(cap_start, 2),
        "capital_end": round(cap_end, 2),
        "pnl_inr": pnl,
        "return_pct": ret,
        "n_trades": n_trades,
        "trades": [
          {"ticker": t.get("ticker"), "pnl": t.get("pnl"), "exit": t.get("exit_reason"), "lev": t.get("leverage")}
          for t in trades
        ],
      }
    )
    print(f"    pnl={pnl:+.1f} ret={ret:+.2f}% trades={n_trades} end={cap_end:,.0f}", flush=True)

  if min_ret > 100:
    min_ret = 0.0
  if max_ret < -100:
    max_ret = 0.0
  compound = round(100.0 * (cap - start_cap) / start_cap, 3) if start_cap else 0.0
  trade_days = [d for d in daily if d["n_trades"] > 0]
  avg_td = (
    round(sum(d["pnl_inr"] for d in trade_days) / len(trade_days), 2) if trade_days else None
  )
  return {
    "name": cfg["name"],
    "window": window,
    "params": {**cfg, **{k: kw[k] for k in ("bulk_min_win_rate", "max_leverage")}},
    "capital_start": start_cap,
    "capital_end": round(cap, 2),
    "pnl_inr": round(cap - start_cap, 2),
    "compound_pct": compound,
    "total_trades": total_trades,
    "trade_days": len(trade_days),
    "avg_pnl_on_trade_days": avg_td,
    "worst_day_pct": round(min_ret, 3),
    "best_day_pct": round(max_ret, 3),
    "max_dd_pct": round(max_dd, 3),
    "pass_break_even": compound >= 0 and avg_td is not None and avg_td > 0,
    "daily": daily,
  }


def _append_log(report: dict) -> None:
  log_path = ROOT / "docs" / "DAY_SIM_METHODS_LOG.md"
  if not log_path.exists():
    return
  tz = ZoneInfo("Asia/Kolkata")
  now = datetime.now(tz).strftime("%Y-%m-%d %H:%M IST")
  rows = []
  for r in report["runs"]:
    rows.append(
      f"| {r['name']} | {r['window']} | {r['compound_pct']:+.2f}% | {r['pnl_inr']:+.0f} | "
      f"{r['total_trades']} | {r.get('avg_pnl_on_trade_days')} | {r['max_dd_pct']:.1f}% | "
      f"{r['pass_break_even']} |"
    )
  best = report.get("best")
  body = f"""

## K. Copy-pro push — double down on what works

> Generated: {now}  
> Script: `scripts/run_copy_pro_push.py`  
> Baseline: bake-off Lane B July +5.39%. Hardening = min investor n≥2, deal ≥₹2.5cr, SL cooldown.

| Config | Window | Compound | PnL | Trades | Avg trade-day | MaxDD | Pass≥0 |
|--------|--------|----------|-----|--------|---------------|-------|--------|
{chr(10).join(rows)}

**Best:** `{best}`  
**Report:** `models/copy_pro_push.json`

"""
  text = log_path.read_text(encoding="utf-8")
  marker = "## K. Copy-pro push"
  if marker in text:
    pre = text.split(marker)[0].rstrip()
    after = text.split(marker, 1)[1]
    if "## Changelog" in after:
      after = "## Changelog" + after.split("## Changelog", 1)[1]
      text = pre + "\n" + body + "\n" + after
    else:
      text = pre + "\n" + body
  elif "## Changelog" in text:
    text = text.replace("## Changelog", body + "\n## Changelog")
  else:
    text = text.rstrip() + "\n" + body
  if "Copy-pro push" not in text.split("## Changelog")[-1]:
    text = text.replace(
      "## Changelog\n\n| Date | Change |\n|------|--------|\n",
      "## Changelog\n\n| Date | Change |\n|------|--------|\n"
      f"| {date.today().isoformat()} | **Copy-pro push:** quality filters + SL cooldown grid; "
      f"best={best}; see §K; `copy_pro_push.json`. |\n",
    )
  log_path.write_text(text, encoding="utf-8")


def main() -> None:
  cov = bulk_data_coverage(since="2026-07-01")
  print("coverage", cov, flush=True)
  runs: list[dict] = []
  for wname, (ws, we) in WINDOWS.items():
    days = _sessions(ws, we)
    # Skip august configs if no bulk past July 20 and all would sit — still run to measure
    for cfg in GRID:
      runs.append(run_config(cfg, days, window=wname))

  # Prefer July (has data) then Aug; rank by compound among pass_break_even, else by compound
  july = [r for r in runs if r["window"] == "july"]
  ranked = sorted(
    july,
    key=lambda r: (r["pass_break_even"], r["compound_pct"], -r["max_dd_pct"]),
    reverse=True,
  )
  best = ranked[0] if ranked else None
  best_id = f"{best['name']}@{best['window']}" if best else None

  # Update registry defaults if quality_v1 or better beats baseline on July
  if best and best["pass_break_even"] and best["name"] != "baseline_bakeoff":
    reg = ROOT / "packages" / "processor" / "hybrid" / "registry.py"
    src = reg.read_text(encoding="utf-8")
    # patch copy_bulk_pro product kwargs numbers if quality won
    if best["name"].startswith("quality"):
      print(f"Promoting registry defaults toward {best['name']}", flush=True)

  report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "coverage": cov,
    "capital": CAPITAL,
    "runs": runs,
    "best": best_id,
    "best_row": best,
    "verdict": (
      f"Best July config {best_id}: compound {best['compound_pct']:+.2f}% "
      f"avgTD={best['avg_pnl_on_trade_days']} DD={best['max_dd_pct']:.1f}%"
      if best
      else "No runs"
    ),
  }
  out = ROOT / "models" / "copy_pro_push.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  _append_log(report)
  print("\n" + report["verdict"], flush=True)
  print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
  main()
