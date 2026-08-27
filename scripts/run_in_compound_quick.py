"""Fast IN compound sweep — OR-width + session-end configs only (post-oracle)."""

from __future__ import annotations

import run_in_compound_search as r

r.CONFIGS = [
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

ORWIDTH_LOG_START = "<!-- AUTO:IN_ORWIDTH_START -->"
ORWIDTH_LOG_END = "<!-- AUTO:IN_ORWIDTH_END -->"
ORWIDTH_REPORT = r.ROOT / "models" / "in_compound_orwidth_report.json"


def main() -> None:
  ist = __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
  end = __import__("datetime").datetime.now(ist).date()
  while end.weekday() >= 5:
    end -= __import__("datetime").timedelta(days=1)
  days = r._trading_days(end, r.N_DAYS)
  print(f"IN OR-width compound quick | {len(r.CONFIGS)} configs")
  print(f"Sessions: {days[0]} -> {days[-1]}")
  results = []
  for cfg in r.CONFIGS:
    name = cfg["name"]
    kw = {k: v for k, v in cfg.items() if k != "name"}
    print(f"  {name} ...", flush=True)
    results.append(r._eval_compound(name, days, kw))
  pass_8 = [x for x in results if x["all_days_ge_8pct"]]
  pass_10 = [x for x in results if x["all_days_ge_10pct"]]
  results.sort(
    key=lambda x: (x["all_days_ge_10pct"], x["all_days_ge_8pct"], x["min_daily_return_pct"], x["compound_total_pct"]),
    reverse=True,
  )
  report = {
    "generated_at": __import__("datetime").datetime.now(ist).isoformat(),
    "market": r.MARKET,
    "min_daily_pct_floor": r.MIN_DAILY_PCT,
    "target_ambition_pct": r.TARGET_AMBITION_PCT,
    "compounding": True,
    "sessions": days,
    "start_capital_inr": r.START_CAPITAL,
    "pass_8pct": pass_8,
    "pass_10pct": pass_10,
    "goal_8_met": len(pass_8) > 0,
    "goal_10_met": len(pass_10) > 0,
    "ranked": results,
  }
  ORWIDTH_REPORT.write_text(__import__("json").dumps(report, indent=2), encoding="utf-8")
  r._patch_methods_log(report, ist, auto_start=ORWIDTH_LOG_START, auto_end=ORWIDTH_LOG_END)
  best = results[0] if results else None
  if pass_10:
    print(f"10% EVERY DAY: {', '.join(x['name'] for x in pass_10)}")
  elif pass_8:
    print(f"8% EVERY DAY: {', '.join(x['name'] for x in pass_8)}")
  elif best:
    print(f"Best min-day: {best['min_daily_return_pct']}% ({best['name']})")
  print(f"Report: {ORWIDTH_REPORT}")


if __name__ == "__main__":
  main()
