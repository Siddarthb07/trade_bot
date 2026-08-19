"""Paper backtest + per-ticker playbook audit + multi-window viability + $10k day estimate.

Uses yfinance daily closes; next-bar fills; 10 bps cost; entry-only signals.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import yfinance as yf

from processor.strategies import mean_rev_bb, mean_rev_chop, mom_cross, trend_follow
from processor.strategy_audit import (
  CANDIDATES,
  build_playbooks,
  hit_rate_ladder,
  load_playbook,
)

UNIVERSE = [
  "RELIANCE.NS",
  "TCS.NS",
  "INFY.NS",
  "HDFCBANK.NS",
  "ICICIBANK.NS",
  "SBIN.NS",
  "AAPL",
  "MSFT",
  "GOOGL",
  "SPY",
  "QQQ",
]

COST_BPS = 10.0
# Alternate windows to stress viability (years ending ~now via yfinance period)
WINDOWS = [
  {"label": "full_5y", "years": 5},
  {"label": "recent_2y", "years": 2},
  {"label": "recent_1y", "years": 1},
]


def _closes(ticker: str, years: int = 5) -> list[float]:
  """Fetch adjusted closes; retry with start/end if period API flakes."""
  from datetime import datetime, timedelta, timezone

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
      print(f"  warn {ticker} attempt {attempt + 1}: {e}", flush=True)
  return []



def _run_strategy(closes: list[float], fn, *, warm: int = 60, min_conf: float = 0.0) -> list[float]:
  rets: list[float] = []
  cost = COST_BPS / 10000.0
  for i in range(warm, len(closes) - 1):
    sig = fn(closes[: i + 1])
    if sig.side not in ("buy", "sell") or sig.confidence < min_conf:
      continue
    fwd = closes[i + 1] / closes[i] - 1.0
    if sig.side == "buy":
      rets.append(fwd - cost)
    else:
      rets.append(-fwd - cost)
  return rets


def _stats(rets: list[float], name: str) -> dict:
  if not rets:
    return {
      "strategy": name,
      "n_trades": 0,
      "hit_rate_pct": None,
      "expectancy": None,
      "total_return_compounded_pct": None,
      "trades_per_year": None,
      "profit_factor": None,
    }
  wins = [r for r in rets if r > 0]
  losses = [r for r in rets if r <= 0]
  eq = 1.0
  for r in rets:
    eq *= 1 + r
  gross_win = sum(wins) if wins else 0.0
  gross_loss = abs(sum(losses)) if losses else 0.0
  return {
    "strategy": name,
    "n_trades": len(rets),
    "hit_rate_pct": round(100.0 * len(wins) / len(rets), 2),
    "expectancy": round(sum(rets) / len(rets), 6),
    "total_return_compounded_pct": round((eq - 1) * 100, 2),
    "avg_win": round(sum(wins) / len(wins), 6) if wins else 0,
    "avg_loss": round(sum(losses) / len(losses), 6) if losses else 0,
    "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
    "trades_per_year": None,
  }


def _run_playbook_router(closes: list[float], ticker: str, *, min_conf: float = 0.70) -> list[float]:
  """Simulate playbook router: use assigned strategy; hybrid if secondary agrees."""
  pb = load_playbook(ticker)
  if not pb or pb.get("status") != "passed" or not pb.get("strategy_id"):
    return []
  primary = CANDIDATES.get(pb["strategy_id"])
  secondary = CANDIDATES.get(pb.get("secondary_strategy_id") or "")
  if primary is None:
    return []
  rets: list[float] = []
  cost = COST_BPS / 10000.0
  for i in range(60, len(closes) - 1):
    window = closes[: i + 1]
    s1 = primary(window)
    if s1.side not in ("buy", "sell"):
      continue
    conf = s1.confidence
    if secondary is not None:
      s2 = secondary(window)
      if s2.side == s1.side:
        conf = 0.6 * s1.confidence + 0.4 * s2.confidence
    if conf < min_conf:
      continue
    # Soft-pass only if ambition_pass for "live-like"; still count soft for paper stats
    fwd = closes[i + 1] / closes[i] - 1.0
    pnl = (fwd - cost) if s1.side == "buy" else (-fwd - cost)
    rets.append(pnl)
  return rets


def _window_report(series: dict[str, list[float]], years: int, label: str) -> dict:
  pooled: dict[str, list[float]] = {
    "mom_cross": [],
    "mean_rev_bb": [],
    "trend_follow": [],
    "mean_rev_chop": [],
    "playbook_router": [],
  }
  per_ticker: dict[str, dict] = {}
  for ticker, closes in series.items():
    if len(closes) < 120:
      per_ticker[ticker] = {"error": "insufficient_bars", "n": len(closes)}
      continue
    m = _run_strategy(closes, mom_cross)
    r = _run_strategy(closes, mean_rev_bb)
    tf = _run_strategy(closes, trend_follow)
    mc = _run_strategy(closes, mean_rev_chop)
    pb = _run_playbook_router(closes, ticker, min_conf=0.70)
    row = {
      "bars": len(closes),
      "mom_cross": _stats(m, "mom_cross"),
      "mean_rev_bb": _stats(r, "mean_rev_bb"),
      "trend_follow": _stats(tf, "trend_follow"),
      "mean_rev_chop": _stats(mc, "mean_rev_chop"),
      "playbook_router": _stats(pb, "playbook_router"),
    }
    for k, v in row.items():
      if isinstance(v, dict) and v.get("n_trades"):
        v["trades_per_year"] = round(v["n_trades"] / max(years, 0.25), 2)
    per_ticker[ticker] = row
    pooled["mom_cross"].extend(m)
    pooled["mean_rev_bb"].extend(r)
    pooled["trend_follow"].extend(tf)
    pooled["mean_rev_chop"].extend(mc)
    pooled["playbook_router"].extend(pb)

  summary = {k: _stats(v, k) for k, v in pooled.items()}
  for k, st in summary.items():
    if st.get("n_trades"):
      st["trades_per_year"] = round(st["n_trades"] / max(years, 0.25), 2)
  return {"label": label, "years": years, "pooled": summary, "per_ticker": per_ticker}


def _hypothetical_10k(pooled: dict, *, capital: float = 10_000.0) -> dict:
  """One trading day: deploy full $10k once at playbook expectancy (or best available)."""
  pb = pooled.get("playbook_router") or {}
  # Prefer playbook; else best expectancy among strategies with trades
  candidates = []
  for name, st in pooled.items():
    if st.get("n_trades") and st.get("expectancy") is not None:
      candidates.append((name, st))
  if pb.get("n_trades") and pb.get("expectancy") is not None:
    chosen_name, chosen = "playbook_router", pb
  elif candidates:
    chosen_name, chosen = max(candidates, key=lambda x: float(x[1]["expectancy"]))
  else:
    return {
      "capital_usd": capital,
      "horizon": "1_trading_day",
      "note": "no_trades_in_backtest",
      "expected_pnl_usd": 0.0,
    }

  exp = float(chosen["expectancy"])
  hit = chosen.get("hit_rate_pct")
  tpy = float(chosen.get("trades_per_year") or 0)
  # Assume at most 1 full-capital trade in a day if strategy fires; expected PnL = capital * expectancy
  expected_pnl = capital * exp
  # If strategy rarely fires, scale by probability of a trade that day (~ tpy / 252)
  p_trade_day = min(1.0, tpy / 252.0) if tpy else 0.0
  expected_pnl_accounting_for_frequency = capital * exp * p_trade_day

  return {
    "capital_usd": capital,
    "horizon": "1_trading_day",
    "strategy_used": chosen_name,
    "hit_rate_pct": hit,
    "expectancy_per_trade": exp,
    "trades_per_year": tpy,
    "prob_trade_on_random_day": round(p_trade_day, 4),
    "if_one_full_capital_trade_fires_expected_pnl_usd": round(expected_pnl, 2),
    "expected_pnl_usd_average_day": round(expected_pnl_accounting_for_frequency, 2),
    "assumptions": [
      "Uses backtest expectancy after 10 bps cost on daily next-bar fills",
      "One full $10k deployment if a signal fires (no intraday pyramiding)",
      "Average-day figure multiplies by historical fire rate (trades/year / 252)",
      "Not a promise of profit; paper simulation only",
    ],
  }


def main() -> None:
  print("Fetching 5y series…", flush=True)
  series_5y: dict[str, list[float]] = {}
  for ticker in UNIVERSE:
    print(f"  {ticker}", flush=True)
    series_5y[ticker] = _closes(ticker, years=5)

  print("Building playbooks (walk-forward)…", flush=True)
  playbooks = build_playbooks(series_5y)

  # Ladder on pooled trend_follow + mean_rev_chop
  ladder_rows = []
  for ticker, closes in series_5y.items():
    if len(closes) < 200:
      continue
    for sid, fn in (("trend_follow", trend_follow), ("mean_rev_chop", mean_rev_chop), ("mom_cross", mom_cross)):
      for row in hit_rate_ladder(closes, fn):
        ladder_rows.append({"ticker": ticker, "strategy": sid, **row})
  ladder = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "rows": ladder_rows,
    "best_ambition": [
      r for r in ladder_rows
      if r.get("hit_rate_pct") is not None
      and r["hit_rate_pct"] >= 85
      and r.get("expectancy") is not None
      and r["expectancy"] > 0
      and r.get("n_trades", 0) >= 10
    ],
  }
  ladder_path = ROOT / "models" / "hit_rate_ladder.json"
  ladder_path.write_text(json.dumps(ladder, indent=2))

  windows_out = []
  # full 5y
  windows_out.append(_window_report(series_5y, 5, "full_5y"))

  # recent windows (re-fetch shorter for alignment with "different years")
  for w in WINDOWS[1:]:
    series: dict[str, list[float]] = {}
    for ticker in UNIVERSE:
      series[ticker] = _closes(ticker, years=w["years"])
    windows_out.append(_window_report(series, w["years"], w["label"]))

  hyp = _hypothetical_10k(windows_out[0]["pooled"], capital=10_000.0)
  hyp_by_window = {
    w["label"]: _hypothetical_10k(w["pooled"], capital=10_000.0) for w in windows_out
  }

  ambition_count = sum(
    1 for p in (playbooks.get("playbooks") or {}).values() if p.get("ambition_pass")
  )
  soft_count = sum(
    1 for p in (playbooks.get("playbooks") or {}).values() if p.get("status") == "passed"
  )

  out = {
    "mode": "paper_playbook_audit",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "cost_bps": COST_BPS,
    "universe": UNIVERSE,
    "measurement": "entry_only_no_ma_state_orb_disabled_on_daily",
    "playbook_summary": {
      "ambition_pass_tickers": ambition_count,
      "soft_pass_tickers": soft_count,
      "path": str(ROOT / "models" / "ticker_playbooks.json"),
    },
    "windows": windows_out,
    "hypothetical_10k_usd_1_day": hyp,
    "hypothetical_10k_by_window": hyp_by_window,
    "ladder_path": str(ladder_path),
    "ladder_ambition_rows": len(ladder["best_ambition"]),
    "disclaimer": "Paper simulation — not live broker fills; not investment advice.",
  }
  path = ROOT / "models" / "paper_5y_backtest.json"
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(out, indent=2))

  print(
    json.dumps(
      {
        "pooled_5y": windows_out[0]["pooled"],
        "playbook_summary": out["playbook_summary"],
        "hypothetical_10k_usd_1_day": hyp,
        "hypothetical_10k_by_window": hyp_by_window,
        "windows": {w["label"]: w["pooled"] for w in windows_out},
        "wrote": str(path),
      },
      indent=2,
    )
  )


if __name__ == "__main__":
  main()
