"""Search for session sim configs that hit >=10% return on EVERY benchmark day.

Sim-only; uses volatile universe + target_return leverage sizing.
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

TARGET = 10.0
CAPITAL = 10_000.0
N_DAYS = 12


def _trading_days(end: date, n: int) -> list[str]:
  out: list[str] = []
  d = end
  while len(out) < n:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d -= timedelta(days=1)
  return list(reversed(out))


CONFIGS: list[dict] = [
  {"name": "tr10_in_25x", "market": "IN", "filter_mode": "target_return", "max_leverage": 25.0,
   "conf_floor": 0.55, "min_or_pct": 0.003, "target_return_pct": 10.0},
  {"name": "tr10_in_50x", "market": "IN", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.0025, "target_return_pct": 10.0},
  {"name": "tr10_in_50x_tight_or", "market": "IN", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.58, "min_or_pct": 0.005, "target_return_pct": 10.0, "tp_override": 0.008},
  {"name": "tr10_in_75x", "market": "IN", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 10.0},
  {"name": "tr10_in_100x", "market": "IN", "filter_mode": "target_return", "max_leverage": 100.0,
   "conf_floor": 0.50, "min_or_pct": 0.002, "target_return_pct": 10.0},
  {"name": "tr10_us_50x", "market": "US", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 10.0, "currency": "USD"},
  {"name": "tr10_us_75x", "market": "US", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.50, "min_or_pct": 0.0015, "target_return_pct": 10.0, "currency": "USD"},
  {"name": "tr10_in_50x_session_end", "market": "IN", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 10.0, "exit_at_session_end": True},
  {"name": "tr10_in_75x_session_end", "market": "IN", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.50, "min_or_pct": 0.002, "target_return_pct": 10.0, "exit_at_session_end": True},
  {"name": "tr10_chase_3x50", "market": "IN", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 10.0, "max_chase_attempts": 3},
  {"name": "tr10_chase_5x75", "market": "IN", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.50, "min_or_pct": 0.002, "target_return_pct": 10.0, "max_chase_attempts": 5,
   "exit_at_session_end": True},
]


def _eval(name: str, days: list[str], cfg: dict) -> dict:
  p = dict(cfg)
  market = p.pop("market", "IN")
  currency = p.pop("currency", "INR" if market == "IN" else "USD")
  daily: list[dict] = []
  min_ret = 999.0
  max_ret = -999.0
  all_pass = True

  for asof in days:
    res = simulate_day(
      asof=asof,
      capital=CAPITAL,
      currency=currency,
      market=market,
      path_mode="session",
      max_positions=1,
      allow_demo_fallback=False,
      **p,
    )
    ret = float(res.get("return_pct") or 0)
    min_ret = min(min_ret, ret)
    max_ret = max(max_ret, ret)
    if ret < TARGET:
      all_pass = False
    daily.append(
      {
        "asof": asof,
        "return_pct": ret,
        "n_trades": res.get("n_trades"),
        "pnl": res.get("realized_pnl"),
        "leverage": res.get("max_leverage"),
        "trades": [
          {"ticker": t["ticker"], "lev": t.get("leverage"), "pnl_pct": t["pnl_pct"], "exit": t["exit_reason"]}
          for t in (res.get("trades") or [])
        ],
      }
    )

  avg = sum(d["return_pct"] for d in daily) / len(daily) if daily else 0
  return {
    "name": name,
    "params": {**p, "market": market, "currency": currency},
    "min_return_pct": round(min_ret, 3),
    "max_return_pct": round(max_ret, 3),
    "avg_return_pct": round(avg, 3),
    "all_days_at_or_above_target": all_pass,
    "days_below_target": sum(1 for d in daily if d["return_pct"] < TARGET),
    "target_return_pct": TARGET,
    "days": daily,
  }


def main() -> None:
  ist = ZoneInfo("Asia/Kolkata")
  end = datetime.now(ist).date()
  while end.weekday() >= 5:
    end -= timedelta(days=1)
  days = _trading_days(end, N_DAYS)

  print(f"Target-10 search | min {TARGET}% EVERY day | {days[0]} -> {days[-1]}")
  results: list[dict] = []
  for cfg in CONFIGS:
    name = cfg["name"]
    kw = {k: v for k, v in cfg.items() if k != "name"}
    print(f"  {name} ...", flush=True)
    results.append(_eval(name, days, kw))

  winners = [r for r in results if r["all_days_at_or_above_target"]]
  results.sort(key=lambda r: (r["all_days_at_or_above_target"], r["min_return_pct"], r["avg_return_pct"]), reverse=True)

  report = {
    "generated_at": datetime.now(ist).isoformat(),
    "target_return_pct_minimum": TARGET,
    "sessions": days,
    "winners": winners,
    "ranked": results,
    "goal_met": len(winners) > 0,
  }
  out = ROOT / "models" / "target_10_search_report.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")

  print()
  print(f"{'config':<22} {'min%':>7} {'avg%':>7} {'max%':>7} {'ALL>=10%':>9}")
  for r in results:
    flag = "YES" if r["all_days_at_or_above_target"] else "no"
    print(f"{r['name']:<22} {r['min_return_pct']:>7.3f} {r['avg_return_pct']:>7.3f} {r['max_return_pct']:>7.3f} {flag:>9}")
  print()
  if winners:
    print(f"GOAL MET: {len(winners)} config(s) hit >={TARGET}% every day")
  else:
    print(f"GOAL NOT MET: best min-day return {results[0]['min_return_pct']}% ({results[0]['name']})")
  print(f"Report: {out}")
  _patch_methods_log(report, ist)


def _patch_methods_log(report: dict, tz: ZoneInfo) -> None:
  """Append target-10 search results into docs/DAY_SIM_METHODS_LOG.md."""
  log_path = ROOT / "docs" / "DAY_SIM_METHODS_LOG.md"
  if not log_path.exists():
    return
  text = log_path.read_text(encoding="utf-8")
  lines = [
    f"Generated: {report.get('generated_at', datetime.now(tz).isoformat())}",
    "",
    f"**Goal met:** {'YES' if report.get('goal_met') else 'NO'}",
    "",
    "| Config | Min% | Avg% | Max% | ALL>=10% |",
    "|--------|------|------|------|----------|",
  ]
  for r in report.get("ranked") or []:
    flag = "YES" if r.get("all_days_at_or_above_target") else "no"
    lines.append(
      f"| {r['name']} | {r.get('min_return_pct')} | {r.get('avg_return_pct')} | "
      f"{r.get('max_return_pct')} | {flag} |"
    )
  if report.get("winners"):
    lines.append("")
    lines.append(f"**Winners:** {', '.join(w['name'] for w in report['winners'])}")
  block = "\n".join(lines)
  start = "<!-- AUTO:TARGET10_START -->"
  end = "<!-- AUTO:TARGET10_END -->"
  if start in text and end in text:
    pre, rest = text.split(start, 1)
    _, post = rest.split(end, 1)
    text = f"{pre}{start}\n{block}\n{end}{post}"
    log_path.write_text(text, encoding="utf-8")
    print(f"Updated: {log_path}")


if __name__ == "__main__":
  main()
