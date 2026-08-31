"""2025 Pattern Forge benchmark — clean PIT, full decision ledger.

Prefers disk cache; falls back to yfinance 1h for older 2025 sessions.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.fo_universe import fo_universe_list
from processor.intraday_bars import fetch_intraday_bars, load_disk_session_bars, pick_interval_for_date
from processor.no_ruin import NoRuinConfig, update_peak
from processor.pattern_forge.ledger import log_run, write_summary
from processor.pattern_forge.session import simulate_pattern_session

MONTHS_2025 = [
  ("january", "2025-01-01", "2025-01-31"),
  ("february", "2025-02-01", "2025-02-28"),
  ("march", "2025-03-01", "2025-03-31"),
  ("april", "2025-04-01", "2025-04-30"),
  ("may", "2025-05-01", "2025-05-31"),
  ("june", "2025-06-01", "2025-06-30"),
  ("july", "2025-07-01", "2025-07-31"),
  ("august", "2025-08-01", "2025-08-31"),
  ("september", "2025-09-01", "2025-09-30"),
  ("october", "2025-10-01", "2025-10-31"),
  ("november", "2025-11-01", "2025-11-30"),
  ("december", "2025-12-01", "2025-12-31"),
]


def sessions(a: str, b: str) -> list[str]:
  sd, ed = date.fromisoformat(a), date.fromisoformat(b)
  out = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def load_bars(ticker: str, asof: str, *, allow_network: bool) -> list[dict]:
  disk = load_disk_session_bars(ticker, asof, interval="5m")
  if len(disk) >= 8:
    return disk
  disk_h = load_disk_session_bars(ticker, asof, interval="1h")
  if len(disk_h) >= 5:
    return disk_h
  if not allow_network:
    return []
  iv = pick_interval_for_date(asof, "5m")
  try:
    return fetch_intraday_bars(ticker, session_date=asof, interval=iv, market="IN")
  except Exception:
    return []


def prior_daily(ticker: str, asof: str, *, allow_network: bool) -> list[dict]:
  d = date.fromisoformat(asof) - timedelta(days=1)
  for _ in range(7):
    if d.weekday() < 5:
      bars = load_bars(ticker, d.isoformat(), allow_network=allow_network)
      if bars:
        return [
          {
            "open": float(bars[0].get("open") or bars[0]["close"]),
            "high": max(float(b.get("high") or b["close"]) for b in bars),
            "low": min(float(b.get("low") or b["close"]) for b in bars),
            "close": float(bars[-1]["close"]),
          }
        ]
    d -= timedelta(days=1)
  return []


def pick_best_candidate(
  asof: str,
  universe: list[str],
  *,
  family: str,
  allow_network: bool,
  long_only: bool,
  hybrid_min_score: float = 0.15,
) -> tuple[str, list[dict], dict] | None:
  """Score FO names; prefer actionable buy (or sell if not long_only) with highest conf."""
  from processor.pattern_forge.session import primary_signal
  from processor.two_sided import normalize_side

  best = None
  best_score = -1.0
  for t in universe:
    bars = load_bars(t, asof, allow_network=allow_network)
    if len(bars) < 6:
      continue
    daily = prior_daily(t, asof, allow_network=allow_network)
    # Market regime from liquid proxy (not sparse session cache)
    from processor.pattern_forge.market_regime_proxy import market_closes_asof

    daily_closes = market_closes_asof(asof, allow_network=True)
    if len(daily_closes) < 20:
      # Fallback: best-effort stock session closes from disk
      daily_closes = []
      d = date.fromisoformat(asof)
      for _ in range(180):
        d -= timedelta(days=1)
        if d.weekday() >= 5:
          continue
        pb = load_bars(t, d.isoformat(), allow_network=False)
        if pb:
          daily_closes.append(float(pb[-1]["close"]))
        if len(daily_closes) >= 55:
          break
      daily_closes = list(reversed(daily_closes))
    primary = primary_signal(
      family,
      session_bars=bars,
      daily_bars_before=daily,
      daily_closes=daily_closes or None,
      long_only=long_only,
      hybrid_min_score=hybrid_min_score,
    )
    side = normalize_side(str(primary.get("side")))
    if side is None:
      continue
    if long_only and side != "long":
      continue
    conf = float(primary.get("confidence") or 0)
    orw = float(primary.get("or_width_pct") or 0)
    hc = primary.get("hybrid_choice") or {}
    hybrid_boost = 0.0
    if hc.get("picked") and hc.get("picked") != "cash":
      scores = hc.get("scores") or {}
      hybrid_boost = float(scores.get(hc["picked"]) or 0) * 2.0
    score = conf * 10.0 + orw * 100.0 + hybrid_boost + (0.5 if side == "long" else 0.0)
    if score > best_score:
      best_score = score
      best = (
        t,
        bars,
        {"primary": primary, "daily": daily, "daily_closes": daily_closes},
      )
  return best


def run_benchmark(
  *,
  family: str,
  capital: float = 10_000.0,
  allow_network: bool = True,
  months: list[tuple[str, str, str]] | None = None,
  universe: list[str] | None = None,
  iteration_id: str | None = None,
  knobs: dict | None = None,
) -> dict:
  knobs = knobs or {}
  run_id = str(uuid.uuid4())[:12]
  long_only = bool(knobs.get("long_only", family in ("hybrid_stock_market", "hybrid", "stock_market_hybrid", "pattern_candle")))
  cfg = NoRuinConfig(
    default_sleeve_frac=float(knobs.get("sleeve_frac", 0.25)),
    max_sleeve_frac=0.5,
    max_daily_loss_pct=float(knobs.get("max_daily_loss_pct", 4.0)),
    max_trade_risk_pct=float(knobs.get("max_trade_risk_pct", 3.0)),
  )
  uni = universe or fo_universe_list()[:12]
  cap = capital
  start = capital
  peak = capital
  month_rows = []
  total_trades = 0
  green_months = 0

  for name, a, b in months or MONTHS_2025:
    m_start = cap
    m_trades = 0
    m_wins = 0
    for asof in sessions(a, b):
      picked = pick_best_candidate(
        asof,
        uni,
        family=family,
        allow_network=allow_network,
        long_only=long_only,
        hybrid_min_score=float(knobs.get("hybrid_min_score", 0.15)),
      )
      if not picked:
        continue
      ticker, bars, meta = picked
      out = simulate_pattern_session(
        asof=asof,
        ticker=ticker,
        session_bars=bars,
        capital=cap,
        starting_capital=start,
        peak_equity=peak,
        family=family,
        daily_bars_before=meta.get("daily") or [],
        daily_closes=meta.get("daily_closes") or None,
        sleeve_frac=cfg.default_sleeve_frac,
        no_ruin_cfg=cfg,
        soft_trail_arm=float(knobs.get("soft_trail_arm", 0.025)),
        soft_trail=float(knobs.get("soft_trail", 0.01)),
        sl=float(knobs.get("sl", 0.01)),
        tau=knobs.get("tau"),
        run_id=run_id,
        iteration_id=iteration_id,
        log_ledger=True,
        long_only=long_only,
        min_confidence=float(knobs.get("min_confidence", 0.0)),
        hybrid_min_score=float(knobs.get("hybrid_min_score", 0.15)),
      )
      day_trades = out.get("trades") or []
      m_trades += len(day_trades)
      m_wins += sum(1 for t in day_trades if float(t.get("pnl") or 0) > 0)
      end = float(out.get("capital_end") or cap)
      peak = update_peak(peak, end)
      cap = end
      if out.get("no_ruin", {}).get("halted"):
        break
    pnl = round(cap - m_start, 2)
    pct = round(100.0 * pnl / m_start, 3) if m_start else 0.0
    if pct > 0:
      green_months += 1
    total_trades += m_trades
    month_rows.append(
      {
        "month": name,
        "capital_start": round(m_start, 2),
        "capital_end": round(cap, 2),
        "month_return_pct": pct,
        "n_trades": m_trades,
        "wins": m_wins,
      }
    )
    print(f"  {name:12} {pct:+7.2f}% trades={m_trades} end={cap:,.2f}", flush=True)

  report = {
    "run_id": run_id,
    "iteration_id": iteration_id,
    "strategy": family,
    "benchmark": "2025",
    "claim": "paper/session-sim; clean PIT; modeled ~30bps RT; not live fills",
    "capital_start": start,
    "capital_end": round(cap, 2),
    "total_return_pct": round(100.0 * (cap - start) / start, 3),
    "green_months": green_months,
    "months_total": len(month_rows),
    "n_trades": total_trades,
    "months": month_rows,
    "knobs": knobs,
    "no_ruin": True,
    "goal": {"green_months_min": 8, "mean_month_positive": True},
    "goal_met": green_months >= 8 and (cap > start),
  }
  log_run(report)
  write_summary(
    {
      "status": "ok",
      "latest_run_id": run_id,
      "family": family,
      "benchmark": "2025",
      "total_return_pct": report["total_return_pct"],
      "green_months": green_months,
      "months_total": report["months_total"],
      "goal_met": report["goal_met"],
      "capital_end": report["capital_end"],
    }
  )
  out_path = ROOT / "models" / "pattern_forge" / f"benchmark_2025_{family}_{run_id}.json"
  out_path.parent.mkdir(parents=True, exist_ok=True)
  out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print("wrote", out_path, flush=True)
  return report


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--family", default="pattern_candle")
  ap.add_argument("--cache-only", action="store_true")
  ap.add_argument("--months", default="", help="comma names e.g. october,november,december")
  args = ap.parse_args()
  months = MONTHS_2025
  if args.months.strip():
    want = {x.strip().lower() for x in args.months.split(",") if x.strip()}
    months = [m for m in MONTHS_2025 if m[0] in want]
  print(f"=== 2025 benchmark family={args.family} cache_only={args.cache_only} ===", flush=True)
  run_benchmark(family=args.family, allow_network=not args.cache_only, months=months)


if __name__ == "__main__":
  main()
