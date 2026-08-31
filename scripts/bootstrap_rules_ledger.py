"""Bootstrap rules ledger from last-week copy-pro tape, then show next-day briefing."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
os.environ.setdefault(
  "POSTGRES_URL",
  "postgresql://smartmoney:changeme@127.0.0.1:5433/smartmoney",
)

from processor.hybrid.rules_ledger import (  # noqa: E402
  RULES_PATH,
  learn_from_session,
  load_rules_ledger,
  read_daily_briefing,
  seed_standing_policies,
)


def main() -> None:
  # Reset to clean standing policies for demo boot
  if RULES_PATH.exists():
    RULES_PATH.unlink()
  seed_standing_policies()

  week = Path("models/copy_pro_last_week_trace.json")
  if week.exists():
    data = json.loads(week.read_text(encoding="utf-8"))
    for day in data.get("daily") or []:
      asof = day["asof"]
      trades = []
      for t in day.get("trades") or []:
        trades.append(
          {
            "ticker": t.get("ticker"),
            "pnl": t.get("pnl"),
            "pnl_pct": t.get("pnl_pct"),
            "exit_reason": (t.get("cause") or {}).get("exit_reason") or t.get("exit_reason"),
            "leverage": t.get("leverage"),
            "bulk_entity": (t.get("bulk_meta") or {}).get("entity_normalized"),
          }
        )
      # normalize exit from cause
      for i, t in enumerate(day.get("trades") or []):
        if not trades[i].get("exit_reason"):
          trades[i]["exit_reason"] = (t.get("cause") or {}).get("exit_reason")
      learn = learn_from_session(
        asof=asof,
        trades=trades,
        session_return_pct=day.get("return_pct"),
        strategy_id="copy_bulk_pro",
      )
      print(f"learned {asof}: {learn['rules_touched']}", flush=True)

  briefing = read_daily_briefing("2026-08-29", mark_read=True)
  print("\n===== MONDAY BRIEFING (2026-08-29) =====", flush=True)
  print(briefing["summary"], flush=True)
  for line in briefing["lines"]:
    print(line, flush=True)
  print("\nexclude_tickers:", briefing["exclude_tickers"], flush=True)
  print("exclude_entities:", briefing["exclude_entities"], flush=True)
  print("sitout:", briefing["sitout"], flush=True)
  print("ledger:", RULES_PATH, flush=True)
  print("active_rules:", len(load_rules_ledger().get("rules") or []), flush=True)


if __name__ == "__main__":
  main()
