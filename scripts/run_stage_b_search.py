"""Stage B: adaptive search + peer-gate ablation report (n>=30 ambition)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import yfinance as yf

from processor.adaptive_edge import (
  MIN_OOS_TRADES,
  TARGET_HIT,
  ablation_peer_gate,
  iterate_until_ambition,
  load_profiles,
)
from processor.profile_validate import validate_profiles

UNIVERSE = [
  "RELIANCE.NS",
  "TCS.NS",
  "INFY.NS",
  "HDFCBANK.NS",
  "ICICIBANK.NS",
  "SBIN.NS",
  "ITC.NS",
  "AXISBANK.NS",
  "AAPL",
  "MSFT",
  "GOOGL",
  "AMZN",
  "META",
  "NVDA",
  "SPY",
  "QQQ",
  "IWM",
]


def _closes(ticker: str, years: int = 5) -> list[float]:
  end = datetime.now(timezone.utc)
  start = end - timedelta(days=int(365.25 * years) + 14)
  for attempt in range(3):
    try:
      if attempt == 0:
        hist = yf.Ticker(ticker).history(period=f"{years}y", auto_adjust=True)
      else:
        hist = yf.download(
          ticker,
          start=start.strftime("%Y-%m-%d"),
          end=end.strftime("%Y-%m-%d"),
          auto_adjust=True,
          progress=False,
          threads=False,
        )
      if hist is None or hist.empty:
        continue
      col = "Close" if "Close" in hist.columns else hist.columns[0]
      series = hist[col]
      if hasattr(series, "columns"):
        series = series.iloc[:, 0]
      out = [float(x) for x in series.tolist() if x == x]
      if out:
        return out
    except Exception as e:
      print(f"  warn {ticker}: {e}", flush=True)
  return []


def main() -> None:
  print(f"Stage B search · target_hit={TARGET_HIT*100:.0f}% · min_oos={MIN_OOS_TRADES}", flush=True)
  series: dict[str, list[float]] = {}
  for t in UNIVERSE:
    print(f"  fetch {t}", flush=True)
    c = _closes(t, years=5)
    if len(c) >= 180:
      series[t] = c
      print(f"    bars={len(c)}", flush=True)

  print(f"Iterate ({len(series)} tickers)…", flush=True)
  result = iterate_until_ambition(series, max_rounds=10)
  best = result.get("best") or {}

  # Ablation on each eligible (or top liquid) ticker using best live params
  live = best.get("live_params") or {}
  tp = float(live.get("tp") or 0.012)
  sl = float(live.get("sl") or 0.022)
  hz = int(live.get("horizon") or 8)
  abl: dict[str, dict] = {}
  for t, closes in series.items():
    abl[t] = ablation_peer_gate(closes, tp=tp, sl=sl, horizon=hz)

  profiles = load_profiles()
  val_errs = validate_profiles(profiles, require_eligible=False)
  eligible = profiles.get("eligible_tickers") or []
  stage_b_pass = len(eligible) >= 3 and not validate_profiles(profiles, require_eligible=True)

  out = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "target_hit_pct": TARGET_HIT * 100,
    "min_oos_trades": MIN_OOS_TRADES,
    "trials": result.get("trials"),
    "best_summary": {
      "eligible_tickers": best.get("eligible_tickers"),
      "ambition_pass_hybrid": best.get("ambition_pass_hybrid"),
      "ambition_pass_pooled": best.get("ambition_pass_pooled"),
      "ambition_pass_tickers": best.get("ambition_pass_tickers"),
      "pooled_holdout_oos": best.get("pooled_holdout_oos"),
      "pooled_holdout_eligible_only": best.get("pooled_holdout_eligible_only"),
      "live_params": live,
    },
    "ablation_peer_gate": abl,
    "ablation_demotions": [t for t, a in abl.items() if a.get("demote_gate_claim")],
    "profile_validation_errors": val_errs,
    "stage_b_pass": stage_b_pass,
    "eligible_tickers": eligible,
    "disclaimer": "Not investment advice. Expanding holdout only; ablation is diagnostic.",
  }
  path = ROOT / "models" / "stage_b_search_report.json"
  path.write_text(json.dumps(out, indent=2), encoding="utf-8")
  # Also refresh adaptive_edge_backtest.json summary for dash/docs
  (ROOT / "models" / "adaptive_edge_backtest.json").write_text(
    json.dumps(
      {
        "generated_at": out["generated_at"],
        "target_hit_pct": TARGET_HIT * 100,
        "min_oos_trades": MIN_OOS_TRADES,
        "trials": result.get("trials"),
        "best": {k: v for k, v in best.items() if k != "per_ticker"},
        "per_ticker": best.get("per_ticker"),
        "stage_b_pass": stage_b_pass,
        "disclaimer": out["disclaimer"],
      },
      indent=2,
    ),
    encoding="utf-8",
  )
  print(
    json.dumps(
      {
        "wrote": str(path),
        "eligible": eligible,
        "stage_b_pass": stage_b_pass,
        "validation_errors": val_errs,
        "ablation_demotions": out["ablation_demotions"],
        "ambition_pass_hybrid": best.get("ambition_pass_hybrid"),
      },
      indent=2,
    ),
    flush=True,
  )


if __name__ == "__main__":
  main()
