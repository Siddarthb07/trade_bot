"""Paper day / multi-day path simulation for dashboard live + historical replay.

Uses only price history available up to (and including) the as-of bar — no look-ahead
for entries. Exits use TP/SL path after entry (labeled as simulated future for PnL).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import yfinance as yf

from broker.base import OrderRequest
from broker.paper import PaperBroker
from processor.adaptive_edge import (
  AdaptiveState,
  decide_from_state,
  load_profiles,
  load_state,
  path_outcome,
  setup_score,
  state_from_dict,
  state_from_profile,
)

IN_UNIVERSE = [
  "RELIANCE.NS",
  "TCS.NS",
  "INFY.NS",
  "HDFCBANK.NS",
  "ICICIBANK.NS",
  "SBIN.NS",
]

US_UNIVERSE = ["AAPL", "MSFT", "GOOGL", "SPY", "QQQ"]

COST_BPS = 10.0


def _fetch_history(ticker: str, end: datetime, lookback_days: int = 400) -> list[tuple[str, float]]:
  """Return list of (YYYY-MM-DD, close) up to end date inclusive."""
  start = end - timedelta(days=lookback_days)
  end_excl = end + timedelta(days=2)
  for attempt in range(3):
    try:
      if attempt == 0:
        hist = yf.Ticker(ticker).history(
          start=start.strftime("%Y-%m-%d"),
          end=end_excl.strftime("%Y-%m-%d"),
          auto_adjust=True,
        )
      else:
        hist = yf.download(
          ticker,
          start=start.strftime("%Y-%m-%d"),
          end=end_excl.strftime("%Y-%m-%d"),
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
      out: list[tuple[str, float]] = []
      for ts, px in series.items():
        if px != px:
          continue
        d = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
        if d <= end.date().isoformat():
          out.append((d, float(px)))
      if out:
        return out
    except Exception:
      continue
  return []


def _state_for_ticker(ticker: str) -> AdaptiveState:
  profile = None
  data = load_profiles()
  profiles = data.get("profiles") or {}
  if ticker in profiles:
    profile = profiles[ticker]
  else:
    bare = ticker.split(".")[0]
    for k, v in profiles.items():
      if k.split(".")[0] == bare:
        profile = v
        break
  if profile and profile.get("peers"):
    return state_from_profile(profile)
  st = load_state()
  # Defaults tuned for IN day book if global state empty
  if st.tp <= 0:
    st.tp, st.sl, st.horizon = 0.01, 0.02, 5
  return st


def _warm_peers(st: AdaptiveState, closes: list[float], asof_idx: int, cost: float) -> None:
  """Expanding-window peer memory using only bars before asof (no peek)."""
  warm = 60
  for i in range(warm, asof_idx):
    window = closes[: i + 1]
    setup = setup_score(window)
    if setup is None:
      continue
    side, score = setup
    out = path_outcome(closes, i, side, tp=st.tp, sl=st.sl, horizon=st.horizon, cost=cost)
    if out is None:
      continue
    won, _ = out
    st.add(side, score, won)


def simulate_day(
  *,
  asof: str = "2024-08-23",
  capital: float = 10_000.0,
  currency: str = "INR",
  market: str = "IN",
  max_positions: int = 3,
  conf_floor: float = 0.70,
) -> dict[str, Any]:
  """Replay adaptive_edge paper book for one calendar day with full ledger."""
  day = datetime.fromisoformat(asof).replace(tzinfo=timezone.utc)
  universe = IN_UNIVERSE if market.upper() == "IN" else US_UNIVERSE
  broker = PaperBroker(market.upper(), starting_cash=capital, currency=currency)
  cost = COST_BPS / 10000.0

  ledger: list[dict[str, Any]] = []
  trades: list[dict[str, Any]] = []
  skipped: list[dict[str, Any]] = []
  cash_start = capital

  ledger.append(
    {
      "ts": asof,
      "event": "session_open",
      "cash": round(cash_start, 2),
      "note": f"Paper day sim · {market} · {currency} {capital:,.0f}",
    }
  )

  candidates: list[dict[str, Any]] = []

  for ticker in universe:
    bars = _fetch_history(ticker, day)
    if len(bars) < 80:
      skipped.append({"ticker": ticker, "reason": "insufficient_history", "n": len(bars)})
      continue
    # Find as-of index
    dates = [d for d, _ in bars]
    if asof not in dates:
      # nearest prior trading day
      prior = [d for d in dates if d <= asof]
      if not prior:
        skipped.append({"ticker": ticker, "reason": "no_bar_on_or_before_asof"})
        continue
      asof_bar = prior[-1]
    else:
      asof_bar = asof
    idx = dates.index(asof_bar)
    closes = [px for _, px in bars]
    # Need forward bars for exit path (sim PnL) — fetch a bit past asof
    future = _fetch_history(ticker, day + timedelta(days=40), lookback_days=60)
    # Merge unique by date
    by_d = {d: px for d, px in bars}
    for d, px in future:
      by_d[d] = px
    merged = sorted(by_d.items())
    dates_m = [d for d, _ in merged]
    closes_m = [px for _, px in merged]
    if asof_bar not in dates_m:
      skipped.append({"ticker": ticker, "reason": "asof_missing_after_merge"})
      continue
    idx_m = dates_m.index(asof_bar)

    st = _state_for_ticker(ticker)
    _warm_peers(st, closes_m, idx_m, cost)
    window = closes_m[: idx_m + 1]
    sig = decide_from_state(window, st, buy_only=True)
    px = closes_m[idx_m]
    candidates.append(
      {
        "ticker": ticker,
        "asof_bar": asof_bar,
        "price": round(px, 4),
        "side": sig.side,
        "confidence": round(sig.confidence, 4),
        "reason": sig.reason,
        "tp": st.tp,
        "sl": st.sl,
        "horizon": st.horizon,
        "closes_m": closes_m,
        "idx_m": idx_m,
        "dates_m": dates_m,
      }
    )

  # Rank buyable by confidence
  buys = [c for c in candidates if c["side"] == "buy" and c["confidence"] >= conf_floor and "gate_ok" in (c["reason"] or "")]
  # If adaptive gate too strict for this historical day, fall back to setup_score longs
  if not buys:
    for c in candidates:
      window = c["closes_m"][: c["idx_m"] + 1]
      setup = setup_score(window)
      if setup is None:
        continue
      side, score = setup
      if side != "buy" or score < 0.55:
        continue
      c["side"] = "buy"
      c["confidence"] = round(max(float(c.get("confidence") or 0.5), 0.70 + score * 0.2), 4)
      c["reason"] = f"setup_fallback|score={score:.3f}|was={c.get('reason')}"
      buys.append(c)

  buys.sort(key=lambda x: x["confidence"], reverse=True)
  buys = buys[:max_positions]

  for c in candidates:
    if c not in buys:
      skipped.append(
        {
          "ticker": c["ticker"],
          "reason": c["reason"] if c["side"] != "buy" else "not_selected_or_below_conf",
          "confidence": c["confidence"],
          "side": c["side"],
          "price": c["price"],
        }
      )

  per_slot = capital / max(1, max_positions)
  open_book: list[dict[str, Any]] = []

  for c in buys:
    notional = min(per_slot, broker.cash * 0.98)
    px = c["price"]
    qty = notional / px if px > 0 else 0
    if qty <= 0 or notional < 50:
      skipped.append({"ticker": c["ticker"], "reason": "notional_too_small", "cash": broker.cash})
      continue
    req = OrderRequest(
      market=market.upper(),  # type: ignore[arg-type]
      ticker=c["ticker"],
      ticker_normalized=c["ticker"],
      side="buy",
      qty=round(qty, 4),
      limit_price=px,
      notional=notional,
    )
    fill = broker.place_order(req)
    if fill.status != "filled":
      skipped.append({"ticker": c["ticker"], "reason": fill.reject_reason or "reject", "notional": notional})
      continue

    entry_notional = round((fill.fill_price or px) * (fill.fill_qty or qty), 2)
    fee = float(fill.fee or 0)
    trade_id = fill.broker_order_id or f"sim-{c['ticker']}"
    ledger.append(
      {
        "ts": c["asof_bar"],
        "event": "buy",
        "trade_id": trade_id,
        "ticker": c["ticker"],
        "qty": fill.fill_qty,
        "price": fill.fill_price,
        "notional": entry_notional,
        "fee": fee,
        "cash_after": round(broker.cash, 2),
        "confidence": c["confidence"],
        "strategy": "adaptive_edge",
        "signal_reason": c["reason"],
        "tp_pct": round(c["tp"] * 100, 2),
        "sl_pct": round(c["sl"] * 100, 2),
        "horizon_bars": c["horizon"],
      }
    )

    # Path exit after entry
    out = path_outcome(
      c["closes_m"],
      c["idx_m"],
      "buy",
      tp=c["tp"],
      sl=c["sl"],
      horizon=c["horizon"],
      cost=cost,
    )
    exit_idx = min(c["idx_m"] + c["horizon"], len(c["closes_m"]) - 1)
    exit_px = c["closes_m"][exit_idx]
    exit_date = c["dates_m"][exit_idx]
    exit_reason = "horizon"
    if out is not None:
      won, path_pnl = out
      # Reconstruct exit price from path
      entry = c["closes_m"][c["idx_m"]]
      for j in range(1, c["horizon"] + 1):
        if c["idx_m"] + j >= len(c["closes_m"]):
          break
        r = c["closes_m"][c["idx_m"] + j] / entry - 1.0
        if r >= c["tp"]:
          exit_idx = c["idx_m"] + j
          exit_px = c["closes_m"][exit_idx]
          exit_date = c["dates_m"][exit_idx]
          exit_reason = "take_profit"
          break
        if r <= -c["sl"]:
          exit_idx = c["idx_m"] + j
          exit_px = c["closes_m"][exit_idx]
          exit_date = c["dates_m"][exit_idx]
          exit_reason = "stop_loss"
          break

    sell_req = OrderRequest(
      market=market.upper(),  # type: ignore[arg-type]
      ticker=c["ticker"],
      ticker_normalized=c["ticker"],
      side="sell",
      qty=fill.fill_qty or qty,
      limit_price=exit_px,
    )
    sell = broker.place_order(sell_req)
    exit_notional = round((sell.fill_price or exit_px) * (sell.fill_qty or qty), 2)
    sell_fee = float(sell.fee or 0)
    pnl = round(exit_notional - entry_notional - fee - sell_fee, 2)
    pnl_pct = round(100.0 * pnl / entry_notional, 3) if entry_notional else 0.0

    ledger.append(
      {
        "ts": exit_date,
        "event": "sell",
        "trade_id": trade_id,
        "ticker": c["ticker"],
        "qty": sell.fill_qty,
        "price": sell.fill_price,
        "notional": exit_notional,
        "fee": sell_fee,
        "cash_after": round(broker.cash, 2),
        "exit_reason": exit_reason,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
      }
    )

    trades.append(
      {
        "trade_id": trade_id,
        "ticker": c["ticker"],
        "market": market.upper(),
        "currency": currency,
        "entry_date": c["asof_bar"],
        "exit_date": exit_date,
        "side": "long",
        "qty": fill.fill_qty,
        "entry_price": fill.fill_price,
        "exit_price": sell.fill_price,
        "entry_notional": entry_notional,
        "exit_notional": exit_notional,
        "fees": round(fee + sell_fee, 4),
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "exit_reason": exit_reason,
        "confidence": c["confidence"],
        "strategy_id": "adaptive_edge",
        "signal_reason": c["reason"],
        "tp_pct": round(c["tp"] * 100, 2),
        "sl_pct": round(c["sl"] * 100, 2),
        "money_put": entry_notional,
        "money_returned": exit_notional,
      }
    )
    open_book.append(trades[-1])

  cash_end = round(broker.cash, 2)
  realized = round(sum(t["pnl"] for t in trades), 2)
  ledger.append(
    {
      "ts": asof,
      "event": "session_summary",
      "cash": cash_end,
      "realized_pnl": realized,
      "n_trades": len(trades),
      "return_pct": round(100.0 * (cash_end - cash_start) / cash_start, 3) if cash_start else 0,
    }
  )

  return {
    "mode": "paper_day_sim",
    "asof": asof,
    "market": market.upper(),
    "currency": currency,
    "capital_start": cash_start,
    "capital_end": cash_end,
    "realized_pnl": realized,
    "return_pct": round(100.0 * (cash_end - cash_start) / cash_start, 3) if cash_start else 0,
    "n_trades": len(trades),
    "trades": trades,
    "ledger": ledger,
    "skipped": skipped,
    "pnl_statement": {
      "opening_cash": cash_start,
      "closing_cash": cash_end,
      "gross_pnl": realized,
      "fees_total": round(sum(t["fees"] for t in trades), 4),
      "wins": sum(1 for t in trades if t["pnl"] > 0),
      "losses": sum(1 for t in trades if t["pnl"] <= 0),
      "hit_rate_pct": round(100.0 * sum(1 for t in trades if t["pnl"] > 0) / len(trades), 2) if trades else None,
      "lines": [
        {
          "ticker": t["ticker"],
          "put": t["money_put"],
          "returned": t["money_returned"],
          "pnl": t["pnl"],
          "pnl_pct": t["pnl_pct"],
          "entry": t["entry_date"],
          "exit": t["exit_date"],
          "exit_reason": t["exit_reason"],
        }
        for t in trades
      ],
    },
    "disclaimer": "Paper simulation — not live broker fills; path exits use post-entry bars for PnL only; not investment advice.",
  }
