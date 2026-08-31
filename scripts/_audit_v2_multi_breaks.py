"""One-shot audit helpers for v2 multi-year break analysis."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PF = ROOT / "models" / "pattern_forge"
trades = json.loads((PF / "v2_multi_year.json").read_text())["trades"]


def month_table(year: int) -> None:
  d = json.loads((PF / f"v2_year_{year}.json").read_text())
  print(f"\n=== {year} month path (capital) ===")
  for mo in d["months"]:
    print(
      f"  {mo['month']:12} {mo['month_return_pct']:+7.2f}% "
      f"end={mo['capital_end']:8.0f} trades={mo['n_trades']} wins={mo.get('wins')}"
    )


def trade_months(year: int) -> None:
  yt = [t for t in trades if t["year"] == year]
  by_m: dict[str, list] = defaultdict(list)
  for t in yt:
    by_m[t["month"]].append(t)
  print(f"\n######## {year} trades n={len(yt)} ########")
  for mo in [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
  ]:
    ts = by_m.get(mo, [])
    if not ts:
      print(f"  {mo:12} NO TRADES")
      continue
    pnl = sum(float(t["pnl"] or 0) for t in ts)
    wins = sum(1 for t in ts if float(t["pnl"] or 0) > 0)
    top = Counter(t["ticker"] for t in ts).most_common(3)
    top_s = [(a.replace(".NS", ""), c) for a, c in top]
    print(f"  {mo:12} n={len(ts):2} W={wins}/{len(ts)} trade_pnl_sum={pnl:+8.0f} top={top_s}")


def may_2023() -> None:
  may = [t for t in trades if t["year"] == 2023 and t["month"] == "may"]
  may = sorted(may, key=lambda t: float(t["pnl"] or 0), reverse=True)
  print("\n=== MAY 2023 trades ===")
  for t in may:
    print(
      f"  {t['asof']} {t['ticker']:14} pnl={float(t['pnl']):+8.2f} "
      f"pct={float(t['pnl_pct']):+7.2f} notional={t['entry_notional']}"
    )
  print("may trade_pnl_sum", round(sum(float(t["pnl"]) for t in may), 2))
  d = json.loads((PF / "v2_year_2023.json").read_text())
  may_m = next(m for m in d["months"] if m["month"] == "may")
  may_cap_pnl = float(may_m["capital_end"]) - float(may_m["capital_start"])
  print("may capital_pnl", round(may_cap_pnl, 2), "year_pnl", d["year_pnl"])
  print("may share of year capital_pnl %", round(100 * may_cap_pnl / float(d["year_pnl"]), 2))
  # without may: reconstruct approximate by removing may from path
  # use month path sum excluding may
  other = sum(
    float(m["capital_end"]) - float(m["capital_start"]) for m in d["months"] if m["month"] != "may"
  )
  print("sum other months capital_pnl", round(other, 2))
  print("year without may capital_path_sum", round(other, 2), "(not same as re-sim)")


def adani() -> None:
  print("\n=== ADANI family trade pnl share ===")
  for y in [2018, 2020, 2022, 2023, 2024, 2025]:
    yt = [t for t in trades if t["year"] == y]
    ad = [t for t in yt if "ADANI" in str(t["ticker"])]
    ypnl = sum(float(t["pnl"] or 0) for t in yt)
    apnl = sum(float(t["pnl"] or 0) for t in ad)
    print(
      y,
      f"adani {len(ad)}/{len(yt)}",
      "apnl",
      round(apnl, 1),
      "all",
      round(ypnl, 1),
      "share%",
      round(100 * apnl / ypnl, 1) if ypnl else None,
    )


def winrates() -> None:
  print("\n=== Year trade win rates ===")
  for y in [2018, 2020, 2022, 2023, 2024, 2025]:
    yt = [t for t in trades if t["year"] == y]
    w = sum(1 for t in yt if float(t["pnl"] or 0) > 0)
    print(y, f"{w}/{len(yt)}", round(100 * w / len(yt), 1) if yt else 0)


if __name__ == "__main__":
  may_2023()
  adani()
  winrates()
  for y in [2018, 2020, 2022, 2023]:
    month_table(y)
    trade_months(y)
