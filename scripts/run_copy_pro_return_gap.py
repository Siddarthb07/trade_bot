"""Diagnose copy-pro return gap: expectancy, exits, capital use, MFE giveback."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
os.environ.setdefault(
  "POSTGRES_URL",
  "postgresql://smartmoney:changeme@127.0.0.1:5433/smartmoney",
)

from processor.intraday_bars import (
  _disk_cache_get,
  default_open_range_bars,
  pick_interval_for_date,
)

CAPITAL = 10_000.0


def _load_months() -> list[dict]:
  mj = json.loads((ROOT / "models" / "copy_pro_may_june_july.json").read_text(encoding="utf-8"))
  months = list(mj.get("months") or [])
  aug_path = ROOT / "models" / "copy_pro_august_ablation.json"
  if aug_path.exists():
    aug = json.loads(aug_path.read_text(encoding="utf-8"))
    months.append(
      {
        "month": "august",
        "compound_pct": aug.get("compound_pct"),
        "pnl_inr": aug.get("pnl_inr"),
        "max_dd_pct": aug.get("max_dd_pct"),
        "n_trades": aug.get("n_trades"),
        "wins": aug.get("wins"),
        "losses": aug.get("losses"),
        "avg_margin_inr": aug.get("avg_margin_inr"),
        "avg_invested_notional_inr": aug.get("avg_invested_notional_inr"),
        "n_flat_days": None,
        "trades": aug.get("trades") or [],
        "daily": aug.get("daily") or [],
      }
    )
  return months


def _bars_from_cache(ticker: str, asof: str) -> tuple[list[dict], str] | None:
  """Disk-cache only (no Yahoo) — May/June 5m is outside Yahoo window."""
  for interval in (pick_interval_for_date(asof, "5m"), "5m", "1h"):
    bars = _disk_cache_get(ticker, asof, interval)
    if bars and len(bars) >= 6:
      return bars, interval
  return None


def _mfe_for_trade(t: dict) -> dict | None:
  ticker = str(t.get("ticker") or "")
  asof = str(t.get("asof") or "")
  if not ticker or not asof:
    return None
  hit = _bars_from_cache(ticker, asof)
  if not hit:
    return {"error": "no_disk_cache"}
  bars, interval = hit
  if len(bars) < 6:
    return {"error": "few_bars", "n_bars": len(bars)}
  or_bars = default_open_range_bars(interval)
  entry_i = min(or_bars, len(bars) - 1)
  entry_px = float(t.get("entry_px") or 0) or float(bars[entry_i].get("close") or 0)
  if entry_px <= 0:
    return {"error": "no_entry"}
  # Prefer bar whose close is nearest to recorded entry_px when present.
  if t.get("entry_px"):
    best_i, best_d = entry_i, abs(float(bars[entry_i].get("close") or 0) - entry_px)
    for i, b in enumerate(bars):
      d = abs(float(b.get("close") or 0) - entry_px)
      if d < best_d:
        best_i, best_d = i, d
    if best_d / entry_px < 0.01:
      entry_i = best_i
      entry_px = float(bars[entry_i].get("close") or entry_px)

  peak = entry_px
  trough = entry_px
  for b in bars[entry_i:]:
    hi = float(b.get("high") or b.get("close") or 0)
    lo = float(b.get("low") or b.get("close") or 0)
    if hi > 0:
      peak = max(peak, hi)
    if lo > 0:
      trough = min(trough, lo)
  exit_px = float(t.get("exit_px") or bars[-1].get("close") or 0)
  mfe_pct = 100.0 * (peak / entry_px - 1.0)
  mae_pct = 100.0 * (trough / entry_px - 1.0)
  realized_pct = float(t.get("pnl_pct") or 0)
  if not realized_pct and exit_px > 0:
    realized_pct = 100.0 * (exit_px / entry_px - 1.0)
  giveback_pct = max(0.0, mfe_pct - realized_pct) if float(t.get("pnl") or 0) > 0 else None
  return {
    "entry_i": entry_i,
    "entry_px": round(entry_px, 4),
    "peak_px": round(peak, 4),
    "trough_px": round(trough, 4),
    "mfe_pct": round(mfe_pct, 3),
    "mae_pct": round(mae_pct, 3),
    "realized_pct": round(realized_pct, 3),
    "giveback_pct": round(giveback_pct, 3) if giveback_pct is not None else None,
    "n_bars": len(bars),
    "interval": interval,
  }


def _month_expectancy(trades: list[dict]) -> dict:
  wins = [t for t in trades if float(t.get("pnl") or 0) > 0]
  losses = [t for t in trades if float(t.get("pnl") or 0) <= 0]
  pnls = [float(t.get("pnl") or 0) for t in trades]
  margins = [float(t.get("margin_inr") or 0) for t in trades if t.get("margin_inr")]
  books = [float(t.get("book_before") or CAPITAL) for t in trades]
  exits: dict[str, int] = {}
  for t in trades:
    k = str(t.get("exit") or t.get("exit_reason") or "?")
    exits[k] = exits.get(k, 0) + 1
  util = []
  for m, b in zip(margins, books):
    if b > 0:
      util.append(100.0 * m / b)
  return {
    "n": len(trades),
    "wins": len(wins),
    "losses": len(losses),
    "win_rate": round(len(wins) / len(trades), 3) if trades else 0,
    "avg_win_inr": round(mean([float(t["pnl"]) for t in wins]), 2) if wins else 0,
    "avg_loss_inr": round(mean([float(t["pnl"]) for t in losses]), 2) if losses else 0,
    "expectancy_inr": round(mean(pnls), 2) if pnls else 0,
    "sum_win": round(sum(float(t["pnl"]) for t in wins), 2),
    "sum_loss": round(sum(float(t["pnl"]) for t in losses), 2),
    "exits": exits,
    "avg_margin_util_pct": round(mean(util), 1) if util else None,
    "avg_idle_cash_pct": round(100.0 - mean(util), 1) if util else None,
  }


def main() -> None:
  months = _load_months()
  out_months = []
  all_givebacks: list[float] = []
  all_mfes_winners: list[float] = []
  mfe_ok = 0
  mfe_fail = 0

  for m in months:
    trades = list(m.get("trades") or [])
    exp = _month_expectancy(trades)
    givebacks = []
    winner_mfes = []
    samples = []
    for t in trades:
      mfe = _mfe_for_trade(t)
      if not mfe or mfe.get("error"):
        mfe_fail += 1
        continue
      mfe_ok += 1
      row = {
        "asof": t.get("asof"),
        "ticker": t.get("ticker"),
        "pnl": t.get("pnl"),
        "exit": t.get("exit") or t.get("exit_reason"),
        **mfe,
      }
      samples.append(row)
      if float(t.get("pnl") or 0) > 0 and mfe.get("giveback_pct") is not None:
        givebacks.append(float(mfe["giveback_pct"]))
        winner_mfes.append(float(mfe["mfe_pct"]))
        all_givebacks.append(float(mfe["giveback_pct"]))
        all_mfes_winners.append(float(mfe["mfe_pct"]))

    out_months.append(
      {
        "month": m.get("month"),
        "compound_pct": m.get("compound_pct"),
        "pnl_inr": m.get("pnl_inr"),
        "max_dd_pct": m.get("max_dd_pct"),
        "expectancy": exp,
        "mfe": {
          "n_ok": len(samples),
          "avg_winner_mfe_pct": round(mean(winner_mfes), 3) if winner_mfes else None,
          "avg_winner_giveback_pct": round(mean(givebacks), 3) if givebacks else None,
          "median_giveback_pct": round(sorted(givebacks)[len(givebacks) // 2], 3) if givebacks else None,
          "samples_head": samples[:8],
        },
      }
    )
    print(
      f"{m.get('month')}: compound={m.get('compound_pct')}% "
      f"WR={exp['win_rate']} exp=₹{exp['expectancy_inr']} "
      f"util={exp['avg_margin_util_pct']}% "
      f"giveback={out_months[-1]['mfe']['avg_winner_giveback_pct']}",
      flush=True,
    )

  compounds = [float(m.get("compound_pct") or 0) for m in months]
  recommendation = {
    "idle_cash_large": any(
      (x.get("expectancy") or {}).get("avg_idle_cash_pct") and (x["expectancy"]["avg_idle_cash_pct"] or 0) >= 35
      for x in out_months
    ),
    "giveback_material": bool(all_givebacks) and mean(all_givebacks) >= 0.8,
    "selection_weak": bool(compounds) and mean(compounds) < 0,
    "primary_lever": "sizing",
  }
  if recommendation["giveback_material"]:
    recommendation["primary_lever"] = "trail"
  elif recommendation["selection_weak"] and not recommendation["idle_cash_large"]:
    recommendation["primary_lever"] = "selection"
  elif recommendation["idle_cash_large"]:
    recommendation["primary_lever"] = "sizing_then_trail"

  out = {
    "generated_at": "2026-08-29",
    "baseline": "ablation_winner_prior_session_cd_wr0",
    "months": out_months,
    "pooled": {
      "mean_compound_pct": round(mean(compounds), 3) if compounds else None,
      "months_ge_10": sum(1 for c in compounds if c >= 10),
      "mfe_ok": mfe_ok,
      "mfe_fail": mfe_fail,
      "avg_winner_mfe_pct": round(mean(all_mfes_winners), 3) if all_mfes_winners else None,
      "avg_winner_giveback_pct": round(mean(all_givebacks), 3) if all_givebacks else None,
    },
    "recommendation": recommendation,
  }
  path = ROOT / "models" / "copy_pro_return_gap.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print("Wrote", path, flush=True)
  print("recommendation", recommendation, flush=True)


if __name__ == "__main__":
  main()
