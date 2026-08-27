"""IN market compound session search: >=8% every day (pass), aim >=10%.

Each session day's ending cash rolls into the next day's starting capital.
Sim-only; not live.
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

MIN_DAILY_PCT = 8.0  # user-acceptable floor
TARGET_AMBITION_PCT = 10.0
START_CAPITAL = 10_000.0
N_DAYS = 12
MARKET = "IN"
CURRENCY = "INR"


def _trading_days(end: date, n: int) -> list[str]:
  out: list[str] = []
  d = end
  while len(out) < n:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d -= timedelta(days=1)
  return list(reversed(out))


# IN-only; target_return_pct drives leverage sizing (8 or 10)
CONFIGS: list[dict] = [
  {"name": "in_tr8_50x", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 8.0},
  {"name": "in_tr10_50x", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 10.0},
  {"name": "in_tr8_75x", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.50, "min_or_pct": 0.002, "target_return_pct": 8.0},
  {"name": "in_tr10_75x", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.50, "min_or_pct": 0.002, "target_return_pct": 10.0},
  {"name": "in_tr8_50x_sess_end", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 8.0, "exit_at_session_end": True},
  {"name": "in_tr10_50x_sess_end", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 10.0, "exit_at_session_end": True},
  {"name": "in_tr8_chase3_50x", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 8.0, "max_chase_attempts": 3},
  {"name": "in_tr10_chase3_50x", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.52, "min_or_pct": 0.002, "target_return_pct": 10.0, "max_chase_attempts": 3},
  {"name": "in_tr8_chase5_75x_sess", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.50, "min_or_pct": 0.0018, "target_return_pct": 8.0,
   "max_chase_attempts": 5, "exit_at_session_end": True},
  {"name": "in_tr10_chase5_75x_sess", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.50, "min_or_pct": 0.0018, "target_return_pct": 10.0,
   "max_chase_attempts": 5, "exit_at_session_end": True},
  {"name": "in_tr8_100x_tight", "filter_mode": "target_return", "max_leverage": 100.0,
   "conf_floor": 0.55, "min_or_pct": 0.004, "target_return_pct": 8.0, "tp_override": 0.01},
  {"name": "in_tr10_100x_tight", "filter_mode": "target_return", "max_leverage": 100.0,
   "conf_floor": 0.55, "min_or_pct": 0.004, "target_return_pct": 10.0, "tp_override": 0.01},
  {"name": "in_tr8_orwidth_sess_50x", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.50, "min_or_pct": 0.0015, "target_return_pct": 8.0,
   "exit_at_session_end": True, "rank_by": "or_width"},
  {"name": "in_tr10_orwidth_sess_50x", "filter_mode": "target_return", "max_leverage": 50.0,
   "conf_floor": 0.50, "min_or_pct": 0.0015, "target_return_pct": 10.0,
   "exit_at_session_end": True, "rank_by": "or_width"},
  {"name": "in_tr8_orwidth_chase5_75x", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.48, "min_or_pct": 0.0015, "target_return_pct": 8.0,
   "exit_at_session_end": True, "rank_by": "or_width", "max_chase_attempts": 5},
  {"name": "in_tr10_orwidth_chase5_75x", "filter_mode": "target_return", "max_leverage": 75.0,
   "conf_floor": 0.48, "min_or_pct": 0.0015, "target_return_pct": 10.0,
   "exit_at_session_end": True, "rank_by": "or_width", "max_chase_attempts": 5},
]


def _eval_compound(name: str, days: list[str], kwargs: dict) -> dict:
  p = dict(kwargs)
  capital = START_CAPITAL
  daily: list[dict] = []
  min_ret = 999.0
  max_ret = -999.0

  for asof in days:
    cap_start = capital
    res = simulate_day(
      asof=asof,
      capital=cap_start,
      currency=CURRENCY,
      market=MARKET,
      path_mode="session",
      max_positions=1,
      allow_demo_fallback=False,
      **p,
    )
    ret = float(res.get("return_pct") or 0)
    cap_end = float(res.get("capital_end") or cap_start)
    capital = cap_end
    min_ret = min(min_ret, ret)
    max_ret = max(max_ret, ret)
    daily.append(
      {
        "asof": asof,
        "return_pct": ret,
        "capital_start": round(cap_start, 2),
        "capital_end": round(cap_end, 2),
        "n_trades": res.get("n_trades"),
        "pnl": res.get("realized_pnl"),
        "trades": [
          {"ticker": t["ticker"], "lev": t.get("leverage"), "pnl_pct": t["pnl_pct"], "exit": t["exit_reason"]}
          for t in (res.get("trades") or [])
        ],
      }
    )

  days_ge_8 = sum(1 for d in daily if d["return_pct"] >= MIN_DAILY_PCT)
  days_ge_10 = sum(1 for d in daily if d["return_pct"] >= TARGET_AMBITION_PCT)
  all_ge_8 = days_ge_8 == len(days) and len(days) > 0
  all_ge_10 = days_ge_10 == len(days) and len(days) > 0
  compound_total_pct = round(100.0 * (capital - START_CAPITAL) / START_CAPITAL, 3)

  return {
    "name": name,
    "params": p,
    "min_daily_return_pct": round(min_ret, 3),
    "max_daily_return_pct": round(max_ret, 3),
    "avg_daily_return_pct": round(sum(d["return_pct"] for d in daily) / len(daily), 3) if daily else 0,
    "days_at_or_above_8pct": days_ge_8,
    "days_at_or_above_10pct": days_ge_10,
    "all_days_ge_8pct": all_ge_8,
    "all_days_ge_10pct": all_ge_10,
    "compound_total_pct": compound_total_pct,
    "final_capital_inr": round(capital, 2),
    "start_capital_inr": START_CAPITAL,
    "days": daily,
  }


LOG_AUTO_START = "<!-- AUTO:IN_COMPOUND_START -->"
LOG_AUTO_END = "<!-- AUTO:IN_COMPOUND_END -->"
REPORT_PATH = ROOT / "models" / "in_compound_search_report.json"


def _patch_methods_log(report: dict, tz: ZoneInfo, *, auto_start: str | None = None, auto_end: str | None = None) -> None:
  log_path = ROOT / "docs" / "DAY_SIM_METHODS_LOG.md"
  if not log_path.exists():
    return
  text = log_path.read_text(encoding="utf-8")
  lines = [
    f"Generated: {report.get('generated_at', datetime.now(tz).isoformat())}",
    "",
    f"**Market:** IN (compounded daily pool)",
    f"**Pass criterion:** every day >= {MIN_DAILY_PCT}% | **Ambition:** >= {TARGET_AMBITION_PCT}%",
    f"**Configs passing 8% every day:** {len(report.get('pass_8pct') or [])}",
    f"**Configs passing 10% every day:** {len(report.get('pass_10pct') or [])}",
    "",
    "| Config | Min/day% | Avg/day% | Compound% | Final INR | ALL>=8% | ALL>=10% |",
    "|--------|----------|----------|-----------|-----------|---------|----------|",
  ]
  for r in report.get("ranked") or []:
    f8 = "YES" if r.get("all_days_ge_8pct") else "no"
    f10 = "YES" if r.get("all_days_ge_10pct") else "no"
    lines.append(
      f"| {r['name']} | {r.get('min_daily_return_pct')} | {r.get('avg_daily_return_pct')} | "
      f"{r.get('compound_total_pct')} | {r.get('final_capital_inr')} | {f8} | {f10} |"
    )
  block = "\n".join(lines)
  start = auto_start or LOG_AUTO_START
  end = auto_end or LOG_AUTO_END
  if start not in text:
    insert = f"\n## IN compound search (8% floor / 10% ambition)\n\n{start}\n(pending)\n{end}\n"
    text += insert
  pre, rest = text.split(start, 1)
  _, post = rest.split(end, 1)
  text = f"{pre}{start}\n{block}\n{end}{post}"
  log_path.write_text(text, encoding="utf-8")
  print(f"Updated: {log_path}")


def main() -> None:
  ist = ZoneInfo("Asia/Kolkata")
  end = datetime.now(ist).date()
  while end.weekday() >= 5:
    end -= timedelta(days=1)
  days = _trading_days(end, N_DAYS)

  print(f"IN compound search | min {MIN_DAILY_PCT}%/day | aim {TARGET_AMBITION_PCT}%+ | pool rolls daily")
  print(f"Sessions: {days[0]} -> {days[-1]} | start INR {START_CAPITAL:,.0f}")
  results: list[dict] = []
  for cfg in CONFIGS:
    name = cfg["name"]
    kw = {k: v for k, v in cfg.items() if k != "name"}
    print(f"  {name} ...", flush=True)
    results.append(_eval_compound(name, days, kw))

  pass_8 = [r for r in results if r["all_days_ge_8pct"]]
  pass_10 = [r for r in results if r["all_days_ge_10pct"]]
  results.sort(
    key=lambda r: (r["all_days_ge_10pct"], r["all_days_ge_8pct"], r["min_daily_return_pct"], r["compound_total_pct"]),
    reverse=True,
  )

  report = {
    "generated_at": datetime.now(ist).isoformat(),
    "market": MARKET,
    "min_daily_pct_floor": MIN_DAILY_PCT,
    "target_ambition_pct": TARGET_AMBITION_PCT,
    "compounding": True,
    "sessions": days,
    "start_capital_inr": START_CAPITAL,
    "pass_8pct": pass_8,
    "pass_10pct": pass_10,
    "goal_8_met": len(pass_8) > 0,
    "goal_10_met": len(pass_10) > 0,
    "ranked": results,
  }
  out = REPORT_PATH
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")

  print()
  hdr = f"{'config':<24} {'min%':>6} {'avg%':>6} {'compound':>9} {'>=8%':>5} {'>=10%':>6}"
  print(hdr)
  print("-" * len(hdr))
  for r in results[:8]:
    print(
      f"{r['name']:<24} {r['min_daily_return_pct']:>6.2f} {r['avg_daily_return_pct']:>6.2f} "
      f"{r['compound_total_pct']:>8.1f}% {'YES' if r['all_days_ge_8pct'] else 'no':>5} "
      f"{'YES' if r['all_days_ge_10pct'] else 'no':>6}"
    )
  print()
  if pass_10:
    print(f"10% EVERY DAY: {', '.join(x['name'] for x in pass_10)}")
  elif pass_8:
    print(f"8% EVERY DAY (pass): {', '.join(x['name'] for x in pass_8)}")
  else:
    best = results[0]
    print(f"No config hit {MIN_DAILY_PCT}% every day. Best min-day: {best['min_daily_return_pct']}% ({best['name']})")
  print(f"Report: {out}")
  _patch_methods_log(report, ist)


if __name__ == "__main__":
  main()
