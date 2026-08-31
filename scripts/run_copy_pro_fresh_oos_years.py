"""Fresh PIT daily OOS for multiple years — same method as 2023 audit leg."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
DASH = Path(r"C:\Users\siddu\Projects\GodFather-core\apps\dashboard\public")

spec = importlib.util.spec_from_file_location(
  "fresh23", ROOT / "scripts" / "run_copy_pro_year_2023_fresh_oos.py"
)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)


def run_year(year: int) -> dict:
  print(f"\n===== FRESH OOS {year} =====", flush=True)
  m.CSV_OUT = ROOT / "models" / f"nse_bulk_fresh_{year}.csv"
  m.OUT = ROOT / "models" / f"copy_pro_year_{year}_fresh_oos.json"
  m.YEAR = year
  rows = m.pull_year(year)
  report = m.backtest(rows, year)
  text = json.dumps(report, indent=2, default=str)
  m.OUT.write_text(text, encoding="utf-8")
  if DASH.exists():
    (DASH / f"year_{year}_fresh.json").write_text(text, encoding="utf-8")
  print(
    f"RESULT {year}: {report['capital_start']} -> {report['capital_end']} "
    f"ret_pct={report['total_return_pct']} trades={report['n_trades']} "
    f"WL={report['wins']}/{report['losses']} sum_pnl={report['capital_accounting']['sum_trade_pnl']}",
    flush=True,
  )
  return report


if __name__ == "__main__":
  years = [int(x) for x in (sys.argv[1:] or ["2025", "2026"])]
  out = {str(y): run_year(y) for y in years}
  summary = {
    y: {
      "capital_end": r["capital_end"],
      "total_return_pct": r["total_return_pct"],
      "n_trades": r["n_trades"],
      "wins": r["wins"],
      "losses": r["losses"],
    }
    for y, r in out.items()
  }
  path = ROOT / "models" / "copy_pro_fresh_oos_compare.json"
  # include 2018/2023 if present
  for y in (2018, 2023):
    p = ROOT / "models" / f"copy_pro_year_{y}_fresh_oos.json"
    if y == 2018:
      # from integrity audit
      audit = ROOT / "models" / "copy_pro_audit_integrity.json"
      if audit.exists():
        a = json.loads(audit.read_text(encoding="utf-8"))
        o = a.get("oos_2018_fresh") or {}
        summary["2018"] = {
          "capital_end": o.get("capital_end"),
          "total_return_pct": o.get("total_return_pct"),
          "n_trades": o.get("n_trades"),
          "wins": o.get("wins"),
          "losses": o.get("losses"),
        }
    elif p.exists():
      r = json.loads(p.read_text(encoding="utf-8"))
      summary[str(y)] = {
        "capital_end": r.get("capital_end"),
        "total_return_pct": r.get("total_return_pct"),
        "n_trades": r.get("n_trades"),
        "wins": r.get("wins"),
        "losses": r.get("losses"),
      }
  path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
  print("SUMMARY", json.dumps(summary, indent=2), flush=True)
