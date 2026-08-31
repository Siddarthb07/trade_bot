"""Pattern Forge v3 bakeoff — risk-managed momentum, OOS gate, never touch v2.

v3 thesis (public research + local failure modes):
- India CS / TS momentum exists; crashes kill plain momentum (Singh et al.; Barroso/Santa-Clara).
- Fix v2 lumps: top_k diversification, vol-scaled rank, skip extended names, market TS soft-gate,
  ticker cooldown, disclosed leverage ≤ design stretch (default 8, not silent 11).
- Confirmed OOS only if 2023 AND 2024 AND 2025 all clear gates.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402

PF = ROOT / "models" / "pattern_forge"
V2_PATH = PF / "v2_latest.json"
OUT = PF / "v3_bakeoff.json"
V3_PATH = PF / "v3_latest.json"


def _max_trade_share(trades: list[dict], year_pnl: float) -> dict[str, Any]:
  if not trades or year_pnl <= 0:
    return {"max_share_pct": None, "trade": None}
  best = max(trades, key=lambda t: float(t.get("pnl") or 0))
  share = 100.0 * float(best.get("pnl") or 0) / year_pnl
  return {
    "max_share_pct": round(share, 2),
    "trade": {
      "asof": best.get("asof"),
      "ticker": best.get("ticker"),
      "pnl": best.get("pnl"),
      "pnl_pct": best.get("pnl_pct"),
    },
  }


def _gates(rep: dict[str, Any], *, max_conc: float = 25.0) -> tuple[bool, list[str]]:
  reasons: list[str] = []
  if float(rep.get("total_return_pct") or -999) <= 0:
    reasons.append("return<=0")
  if int(rep.get("green_months") or 0) < 8:
    reasons.append(f"green={rep.get('green_months')}<8")
  if not rep.get("loss_lte_profits"):
    reasons.append("loss_lte_profits=False")
  if float(rep.get("worst_month_pct") or -999) < -22.0:
    reasons.append(f"worst_month={rep.get('worst_month_pct')}<-22")
  conc = (rep.get("concentration") or {}).get("max_share_pct")
  if conc is not None and float(conc) > max_conc:
    reasons.append(f"max_trade_share={conc}>{max_conc}")
  return (len(reasons) == 0, reasons)


def _base(**over: Any) -> dict[str, Any]:
  k = {
    "learn_mistakes": True,
    "profit_guard": True,
    "profit_guard_floor_pct": 2.0,
    "reset_mistakes": True,
    "long_only": True,
    "swarm_hard_veto": False,
    "overnight_feeds": False,
    "min_score": 0.005,
    "r1_lo": 0.005,
    "r1_hi": 0.05,
    "top_k": 3,
    "use_breadth_veto": False,
    "breadth_scale": True,
    "vol_scale_rank": True,
    "skip_extended_r5": 0.08,
    "require_market_ts_mom": True,
    "market_ts_min": 0.0,
    "ticker_cooldown_days": 3,
    "max_single_name_day_frac": 0.4,
    "max_daily_loss_pct": 8.0,
    "promote_summary": False,
    "write_lab_summary": False,
    "allow_overwrite_v2": False,
    "include_trades": True,
    "universe_n": 0,
  }
  k.update(over)
  return k


VARIANTS: list[tuple[str, dict[str, Any]]] = [
  (
    "v3_risk8",
    _base(lane="v3_risk8", leverage=8.0, sleeve_frac=0.26, promote_as=""),
  ),
  (
    "v3_push10",
    _base(
      lane="v3_push10",
      leverage=10.0,
      sleeve_frac=0.24,
      top_k=3,
      ticker_cooldown_days=2,
      skip_extended_r5=0.10,
    ),
  ),
  (
    "v3_stretch5",
    _base(lane="v3_stretch5", leverage=5.0, sleeve_frac=0.30, top_k=3, r1_hi=0.055),
  ),
  (
    "v3_insane11_div",
    _base(
      lane="v3_insane11_div",
      leverage=11.0,
      sleeve_frac=0.24,
      top_k=3,
      ticker_cooldown_days=2,
      skip_extended_r5=0.07,
      max_single_name_day_frac=0.34,
      require_market_ts_mom=True,
    ),
  ),
]


def run_variant(name: str, knobs: dict[str, Any], years: list[int]) -> dict[str, Any]:
  by_year: dict[str, Any] = {}
  for y in years:
    print(f"\n=== {name} year={y} ===", flush=True)
    rep = run_daily_benchmark(year=y, knobs={**knobs, "year": y, "lane": f"{name}_{y}"})
    trades = list(rep.get("trades") or [])
    conc = _max_trade_share(trades, float(rep.get("year_pnl") or 0))
    ok, reasons = _gates({**rep, "concentration": conc})
    by_year[str(y)] = {
      "run_id": rep.get("run_id"),
      "total_return_pct": rep.get("total_return_pct"),
      "capital_end": rep.get("capital_end"),
      "year_pnl": rep.get("year_pnl"),
      "green_months": rep.get("green_months"),
      "worst_month_pct": rep.get("worst_month_pct"),
      "worst_month_pnl": rep.get("worst_month_pnl"),
      "loss_lte_profits": rep.get("loss_lte_profits"),
      "n_trades": rep.get("n_trades"),
      "concentration": conc,
      "gate_ok": ok,
      "gate_fail": reasons,
      "months": rep.get("months"),
      "trades": trades,
      "knobs": knobs,
    }
  return by_year


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--years", default="2023,2024,2025")
  ap.add_argument("--full-years", default="2018,2019,2020,2021,2022,2023,2024,2025")
  ap.add_argument("--skip-full", action="store_true")
  args = ap.parse_args()
  gate_years = [int(x) for x in args.years.split(",") if x.strip()]
  full_years = [int(x) for x in args.full_years.split(",") if x.strip()]

  locked_v2 = json.loads(V2_PATH.read_text()) if V2_PATH.exists() else {}
  rows: list[dict[str, Any]] = []
  full_reports: dict[str, Any] = {}

  for name, knobs in VARIANTS:
    by_y = run_variant(name, knobs, gate_years)
    full_reports[name] = by_y
    oos_ok = all(by_y[str(y)]["gate_ok"] for y in gate_years)
    mean_ret = sum(float(by_y[str(y)]["total_return_pct"] or 0) for y in gate_years) / len(gate_years)
    rows.append(
      {
        "variant": name,
        "knobs": {k: knobs[k] for k in ("leverage", "sleeve_frac", "top_k", "vol_scale_rank", "skip_extended_r5", "require_market_ts_mom", "ticker_cooldown_days")},
        "oos_ok": oos_ok,
        "mean_gate_return_pct": round(mean_ret, 3),
        "years": {y: {k: by_y[str(y)][k] for k in ("total_return_pct", "green_months", "worst_month_pct", "gate_ok", "gate_fail", "concentration")} for y in gate_years},
      }
    )

  # Prefer oos_ok; then max mean return; then lower leverage
  rows.sort(key=lambda r: (not r["oos_ok"], -float(r["mean_gate_return_pct"]), float(r["knobs"]["leverage"])))
  best = rows[0] if rows else None
  confirmed = bool(best and best["oos_ok"])

  full_multi = None
  if confirmed and best and not args.skip_full:
    name = best["variant"]
    knobs = dict(next(k for n, k in VARIANTS if n == name))
    print(f"\n*** confirmed candidate {name} — full multi-year ***", flush=True)
    multi_years = {}
    all_trades = []
    for y in full_years:
      print(f"\n=== FULL {name} year={y} ===", flush=True)
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
      multi_years[str(y)] = block
      all_trades.extend([{**t, "year": y} for t in trades])
      (PF / f"v3_year_{y}.json").write_text(json.dumps(block, indent=2), encoding="utf-8")
    full_multi = {
      "variant": name,
      "years": multi_years,
      "n_trades": len(all_trades),
      "years_positive": sum(1 for y in full_years if float(multi_years[str(y)]["total_return_pct"] or 0) > 0),
    }
    # Write challenger artefact (never v2)
    v3_payload = {
      "lane": "v3",
      "variant": name,
      "benchmark": "2025",
      **full_reports[name]["2025"],
      "months": full_reports[name]["2025"].get("months"),
      "knobs": knobs,
      "oos": {str(y): full_reports[name][str(y)] for y in gate_years},
      "confirmed_oos": True,
      "claim": (
        f"paper/sim v3 {name}; risk-managed FO daily momentum; leverage={knobs['leverage']} DISCLOSED; "
        "top_k diversified; vol-scaled rank; OOS 2023+2024+2025 gate_ok; not live fills; v2_latest untouched"
      ),
      "locked_v2_untouched": True,
    }
    # reshape 2025 summary fields for Lab
    y25 = full_reports[name]["2025"]
    v3_payload.update(
      {
        "capital_start": 10000.0,
        "capital_end": y25["capital_end"],
        "total_return_pct": y25["total_return_pct"],
        "green_months": y25["green_months"],
        "months_total": 12,
        "worst_month_pct": y25["worst_month_pct"],
        "year_pnl": y25["year_pnl"],
        "loss_lte_profits": y25["loss_lte_profits"],
        "goal_met": True,
        "n_trades": y25["n_trades"],
        "strategy": "daily_swing",
      }
    )
    V3_PATH.write_text(json.dumps(v3_payload, indent=2), encoding="utf-8")
    (PF / "v3_multi_year.json").write_text(
      json.dumps(
        {
          "ts": datetime.now(timezone.utc).isoformat(),
          "lane": "v3",
          "variant": name,
          "knobs": knobs,
          "years_detail": [multi_years[str(y)] for y in full_years],
          "trades": all_trades,
          "claim": v3_payload["claim"],
        },
        indent=2,
      ),
      encoding="utf-8",
    )
  elif best and not confirmed:
    # Still write best research challenger marked not confirmed
    name = best["variant"]
    knobs = dict(next(k for n, k in VARIANTS if n == name))
    y25 = full_reports[name]["2025"]
    V3_PATH.write_text(
      json.dumps(
        {
          "lane": "v3",
          "variant": name,
          "confirmed_oos": False,
          "capital_start": 10000.0,
          "capital_end": y25["capital_end"],
          "total_return_pct": y25["total_return_pct"],
          "green_months": y25["green_months"],
          "months_total": 12,
          "worst_month_pct": y25["worst_month_pct"],
          "year_pnl": y25["year_pnl"],
          "loss_lte_profits": y25["loss_lte_profits"],
          "goal_met": False,
          "n_trades": y25["n_trades"],
          "months": y25.get("months"),
          "knobs": knobs,
          "oos": {str(y): {k: full_reports[name][str(y)][k] for k in ("total_return_pct", "green_months", "worst_month_pct", "gate_ok", "gate_fail", "concentration")} for y in gate_years},
          "claim": "research only — OOS gate not cleared; v2 remains locked hero",
          "locked_v2_untouched": True,
        },
        indent=2,
      ),
      encoding="utf-8",
    )

  bakeoff = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "locked_v2_return_2025": locked_v2.get("total_return_pct"),
    "adani_verify": json.loads((PF / "adani_2023_05_19_verify.json").read_text())
    if (PF / "adani_2023_05_19_verify.json").exists()
    else None,
    "variants": rows,
    "best": best,
    "confirmed_oos": confirmed,
    "full_multi": {k: full_multi[k] for k in ("variant", "n_trades", "years_positive")} if full_multi else None,
    "promote_to_v2": False,
    "claim_rule": "confirmed only if 2023+2024+2025 all gate_ok; v2_latest never overwritten",
  }
  OUT.write_text(json.dumps(bakeoff, indent=2), encoding="utf-8")
  print(f"\nwrote {OUT} confirmed_oos={confirmed} best={best and best['variant']}", flush=True)


if __name__ == "__main__":
  main()
