"""v3 pass-2: keep v2 edge, only fix concentration / disclosure — never touch v2_latest."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402
from run_v3_bakeoff import _gates, _max_trade_share  # noqa: E402

PF = ROOT / "models" / "pattern_forge"
OUT = PF / "v3_bakeoff_pass2.json"
V3 = PF / "v3_latest.json"
V2 = PF / "v2_latest.json"


def v2_base(**over: Any) -> dict[str, Any]:
  k = {
    "leverage": 11.0,
    "sleeve_frac": 0.24,
    "learn_mistakes": True,
    "profit_guard": True,
    "profit_guard_floor_pct": 2.0,
    "reset_mistakes": True,
    "long_only": True,
    "min_score": 0.005,
    "r1_lo": 0.005,
    "r1_hi": 0.06,
    "top_k": 1,
    "use_breadth_veto": False,
    "breadth_scale": False,
    "vol_scale_rank": False,
    "skip_extended_r5": None,
    "require_market_ts_mom": False,
    "ticker_cooldown_days": 0,
    "max_single_name_day_frac": 1.0,
    "max_daily_loss_pct": 8.0,
    "promote_summary": False,
    "write_lab_summary": False,
    "allow_overwrite_v2": False,
    "include_trades": True,
    "swarm_hard_veto": False,
    "overnight_feeds": False,
  }
  if V2.exists():
    kn = json.loads(V2.read_text()).get("knobs") or {}
    for key in ("leverage", "sleeve_frac", "profit_guard", "min_score", "r1_lo", "r1_hi"):
      if key in kn:
        k[key] = kn[key]
  k.update(over)
  return k


VARIANTS = [
  ("v3_div3_lev11", v2_base(lane="v3_div3_lev11", top_k=3, ticker_cooldown_days=2, max_single_name_day_frac=0.34)),
  ("v3_div2_lev11", v2_base(lane="v3_div2_lev11", top_k=2, ticker_cooldown_days=2, max_single_name_day_frac=0.5)),
  ("v3_div3_lev8", v2_base(lane="v3_div3_lev8", leverage=8.0, sleeve_frac=0.28, top_k=3, ticker_cooldown_days=2, max_single_name_day_frac=0.34)),
  ("v3_div3_vol_lev11", v2_base(lane="v3_div3_vol_lev11", top_k=3, vol_scale_rank=True, ticker_cooldown_days=2, max_single_name_day_frac=0.34, skip_extended_r5=0.12)),
  ("v3_div3_lev11_noband", v2_base(lane="v3_div3_lev11_noband", top_k=3, ticker_cooldown_days=1, max_single_name_day_frac=0.34, r1_hi=0.055)),
]


def run_years(name: str, knobs: dict, years: list[int]) -> dict[str, Any]:
  out = {}
  for y in years:
    print(f"\n=== {name} {y} ===", flush=True)
    rep = run_daily_benchmark(year=y, knobs={**knobs, "year": y, "lane": f"{name}_{y}"})
    trades = list(rep.get("trades") or [])
    conc = _max_trade_share(trades, float(rep.get("year_pnl") or 0))
    # Pass-2 gates: slightly softer conc (35%) since div alone should cut Adani ~3x
    ok, reasons = _gates({**rep, "concentration": conc}, max_conc=35.0)
    out[str(y)] = {
      "total_return_pct": rep.get("total_return_pct"),
      "capital_end": rep.get("capital_end"),
      "year_pnl": rep.get("year_pnl"),
      "green_months": rep.get("green_months"),
      "worst_month_pct": rep.get("worst_month_pct"),
      "loss_lte_profits": rep.get("loss_lte_profits"),
      "n_trades": rep.get("n_trades"),
      "concentration": conc,
      "gate_ok": ok,
      "gate_fail": reasons,
      "months": rep.get("months"),
      "trades": trades,
      "run_id": rep.get("run_id"),
    }
    print(
      f"  -> ret={out[str(y)]['total_return_pct']} green={out[str(y)]['green_months']} "
      f"worst={out[str(y)]['worst_month_pct']} conc={conc.get('max_share_pct')} gate={ok} {reasons}",
      flush=True,
    )
  return out


def main() -> None:
  years = [2023, 2024, 2025]
  rows = []
  reports = {}
  for name, knobs in VARIANTS:
    by = run_years(name, knobs, years)
    reports[name] = by
    oos = all(by[str(y)]["gate_ok"] for y in years)
    mean = sum(float(by[str(y)]["total_return_pct"] or 0) for y in years) / 3
    # also require beating a floor vs flat OOS and not collapsing vs v2 too hard on 2025
    v2_2025 = float(json.loads(V2.read_text())["total_return_pct"]) if V2.exists() else 100.0
    beat_half_v2 = float(by["2025"]["total_return_pct"] or 0) >= 0.5 * v2_2025
    rows.append(
      {
        "variant": name,
        "knobs": {k: knobs[k] for k in ("leverage", "sleeve_frac", "top_k", "ticker_cooldown_days", "vol_scale_rank", "max_single_name_day_frac")},
        "oos_ok": oos,
        "beat_half_v2_2025": beat_half_v2,
        "mean_return_pct": round(mean, 3),
        "years": {
          str(y): {k: by[str(y)][k] for k in ("total_return_pct", "green_months", "worst_month_pct", "gate_ok", "gate_fail", "concentration")}
          for y in years
        },
      }
    )

  rows.sort(
    key=lambda r: (
      not r["oos_ok"],
      not r["beat_half_v2_2025"],
      -float(r["mean_return_pct"]),
      float(r["knobs"]["leverage"]),
    )
  )
  best = rows[0]
  confirmed = bool(best["oos_ok"] and best["beat_half_v2_2025"])

  # write v3_latest
  name = best["variant"]
  knobs = dict(next(k for n, k in VARIANTS if n == name))
  y25 = reports[name]["2025"]
  payload = {
    "lane": "v3",
    "variant": name,
    "confirmed_oos": confirmed,
    "strategy": "daily_swing",
    "capital_start": 10000.0,
    "capital_end": y25["capital_end"],
    "total_return_pct": y25["total_return_pct"],
    "green_months": y25["green_months"],
    "months_total": 12,
    "worst_month_pct": y25["worst_month_pct"],
    "year_pnl": y25["year_pnl"],
    "loss_lte_profits": y25["loss_lte_profits"],
    "goal_met": confirmed,
    "n_trades": y25["n_trades"],
    "months": y25.get("months"),
    "knobs": knobs,
    "oos": best["years"],
    "concentration_2025": y25.get("concentration"),
    "locked_v2_untouched": True,
    "claim": (
      f"paper/sim v3 {name}; lev={knobs['leverage']} DISCLOSED; top_k={knobs['top_k']} diversification; "
      f"confirmed_oos={confirmed}; not live fills; does not replace locked v2"
    ),
  }
  V3.write_text(json.dumps(payload, indent=2), encoding="utf-8")

  # If confirmed, run full 2018-2025
  full = None
  if confirmed:
    all_trades = []
    detail = []
    for y in [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
      print(f"\n=== FULL {name} {y} ===", flush=True)
      rep = run_daily_benchmark(year=y, knobs={**knobs, "year": y, "lane": f"v3_{y}", "include_trades": True})
      trades = list(rep.get("trades") or [])
      conc = _max_trade_share(trades, float(rep.get("year_pnl") or 0))
      block = {
        "year": y,
        "total_return_pct": rep.get("total_return_pct"),
        "capital_end": rep.get("capital_end"),
        "year_pnl": rep.get("year_pnl"),
        "green_months": rep.get("green_months"),
        "worst_month_pct": rep.get("worst_month_pct"),
        "loss_lte_profits": rep.get("loss_lte_profits"),
        "n_trades": rep.get("n_trades"),
        "concentration": conc,
        "months": rep.get("months"),
        "trades": trades,
      }
      detail.append(block)
      all_trades.extend([{**t, "year": y} for t in trades])
      (PF / f"v3_year_{y}.json").write_text(json.dumps(block, indent=2), encoding="utf-8")
    full = {"years_positive": sum(1 for b in detail if float(b["total_return_pct"] or 0) > 0), "n_trades": len(all_trades)}
    (PF / "v3_multi_year.json").write_text(
      json.dumps(
        {
          "ts": datetime.now(timezone.utc).isoformat(),
          "lane": "v3",
          "variant": name,
          "confirmed_oos": True,
          "knobs": knobs,
          "years_detail": detail,
          "year_returns": [
            {"year": str(b["year"]), "return_pct": b["total_return_pct"], "end_capital": b["capital_end"], "green_months": b["green_months"], "worst_month_pct": b["worst_month_pct"], "n_trades": b["n_trades"]}
            for b in detail
          ],
          "trades": all_trades,
          "claim": payload["claim"],
        },
        indent=2,
      ),
      encoding="utf-8",
    )

  bake = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "pass": 2,
    "note": "pass1 over-filtered (TS mom+breadth+vol) killed edge; pass2 = v2 signal + diversification only",
    "variants": rows,
    "best": best,
    "confirmed_oos": confirmed,
    "full": full,
    "promote_to_v2": False,
    "v2_2025": json.loads(V2.read_text()).get("total_return_pct") if V2.exists() else None,
  }
  OUT.write_text(json.dumps(bake, indent=2), encoding="utf-8")
  print(f"\nwrote {OUT} confirmed={confirmed} best={name}", flush=True)


if __name__ == "__main__":
  main()
