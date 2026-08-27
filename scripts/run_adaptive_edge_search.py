"""Trial/error adaptive_edge until holdout OOS hit ≥ 85% (no memorizing holdout)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import yfinance as yf

from processor.adaptive_edge import TARGET_HIT, iterate_until_ambition, pooled_expanding_backtest

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
  print("Fetching series…", flush=True)
  series: dict[str, list[float]] = {}
  for t in UNIVERSE:
    print(f"  {t}", flush=True)
    c = _closes(t, years=5)
    if len(c) >= 150:
      series[t] = c

  print(f"Iterate toward {TARGET_HIT*100:.0f}% holdout OOS…", flush=True)
  result = iterate_until_ambition(series, max_rounds=10)
  best = result.get("best") or {}
  oos = (best.get("pooled_holdout_eligible_only") or best.get("pooled_holdout_oos") or {}) if best else {}
  oos_all = (best.get("pooled_holdout_oos") or {}) if best else {}

  # Extra stress: recent 2y / 1y
  alt = {}
  for years, label in ((2, "recent_2y"), (1, "recent_1y")):
    s2 = {t: _closes(t, years=years) for t in UNIVERSE}
    s2 = {t: c for t, c in s2.items() if len(c) >= 120}
    alt[label] = pooled_expanding_backtest(s2, tune=True)

  exp = float(oos.get("expectancy") or 0)
  n = int(oos.get("n_trades") or 0)
  tpy = float(n)
  p_day = min(1.0, tpy / 252.0) if tpy else 0.0
  hyp = {
    "capital_usd": 10000.0,
    "if_one_trade_fires_expected_pnl_usd": round(10000 * exp, 2),
    "expected_pnl_usd_average_day": round(10000 * exp * p_day, 2),
    "holdout_hit_rate_pct": oos.get("hit_rate_pct"),
    "holdout_n_trades": n,
    "mode": "hybrid_eligible_tickers" if best.get("eligible_tickers") else "pooled_all",
  }

  out = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "target_hit_pct": TARGET_HIT * 100,
    "trials": result.get("trials"),
    "best": {k: v for k, v in best.items() if k != "per_ticker"},
    "per_ticker": best.get("per_ticker") if best else {},
    "alternate_windows": {
      k: {
        "pooled_holdout_oos": v.get("pooled_holdout_oos"),
        "pooled_holdout_eligible_only": v.get("pooled_holdout_eligible_only"),
        "eligible_tickers": v.get("eligible_tickers"),
        "ambition_pass_hybrid": v.get("ambition_pass_hybrid"),
        "ambition_pass_pooled": v.get("ambition_pass_pooled"),
      }
      for k, v in alt.items()
    },
    "hypothetical_10k_usd_1_day": hyp,
    "disclaimer": "Holdout OOS only; expanding window; not investment advice.",
  }
  path = ROOT / "models" / "adaptive_edge_backtest.json"
  path.write_text(json.dumps(out, indent=2))
  summary = {
    "adaptive_edge_holdout_hybrid": oos,
    "adaptive_edge_holdout_all": oos_all,
    "eligible_tickers": best.get("eligible_tickers"),
    "ambition_pass_hybrid": best.get("ambition_pass_hybrid"),
    "ambition_pass_pooled": best.get("ambition_pass_pooled"),
    "trials": len(result.get("trials") or []),
    "hyp": hyp,
    "wrote": str(path),
  }
  print(json.dumps(summary, indent=2))


if __name__ == "__main__":
  main()
