"""Paper day / session simulation for dashboard live + historical replay.

Modes:
- daily: EOD closes + path TP/SL (research only; not session fills)
- session: same-day intraday bars + modeled costs (Stage A truth path)

setup_fallback never counts toward edge_metrics_valid — demo badge only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import yfinance as yf

from broker.base import OrderRequest
from broker.paper import PaperBroker
from broker.sizing import confidence_leverage, leverage_for_target
from processor.adaptive_edge import (
  AdaptiveState,
  decide_from_state,
  load_profiles,
  load_state,
  path_outcome,
  setup_score,
  state_from_profile,
)
from processor.costs import cost_fraction, cost_model_for
from processor.intraday_bars import (
  default_open_range_bars,
  fetch_intraday_bars,
  pick_interval_for_date,
  session_closes,
)
from processor.session_guard import apply_session_guards, daily_loss_halted, session_return_pct
from processor.strategies import intraday_orb, market_regime, session_or_breakout

ORWIDTH_GUARD_DEFAULTS = {
  "max_daily_loss_pct": 6.0,
  "max_trade_risk_pct": 6.0,
  "intraday_stop_with_session_end": True,
  "max_chase_attempts": 2,
}

IN_UNIVERSE = [
  "RELIANCE.NS",
  "TCS.NS",
  "INFY.NS",
  "HDFCBANK.NS",
  "ICICIBANK.NS",
  "SBIN.NS",
]

IN_UNIVERSE_VOLATILE = IN_UNIVERSE + [
  "TATASTEEL.NS",
  "VEDL.NS",
  "HINDALCO.NS",
  "ADANIENT.NS",
  "JSWSTEEL.NS",
  "BAJFINANCE.NS",
  "MARUTI.NS",
  "WIPRO.NS",
]

US_UNIVERSE = ["AAPL", "MSFT", "GOOGL", "SPY", "QQQ"]

US_UNIVERSE_VOLATILE = US_UNIVERSE + ["TSLA", "NVDA", "AMD", "META", "COIN"]


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
          auto_adjust=False,
        )
      else:
        hist = yf.download(
          ticker,
          start=start.strftime("%Y-%m-%d"),
          end=end_excl.strftime("%Y-%m-%d"),
          auto_adjust=False,
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
  if st.tp <= 0:
    st.tp, st.sl, st.horizon = 0.01, 0.02, 5
  return st


def _warm_peers(st: AdaptiveState, closes: list[float], asof_idx: int, cost: float) -> None:
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


def _simulate_session_day(
  *,
  asof: str,
  capital: float,
  currency: str,
  market: str,
  max_positions: int,
  conf_floor: float,
  allow_demo_fallback: bool,
  filter_mode: str = "strict",
  tp_override: float | None = None,
  sl_override: float | None = None,
  horizon_override: int | None = None,
  peer_target: float | None = None,
  min_fire: float | None = None,
  skip_peer_gate: bool | None = None,
  regime_allow: list[str] | None = None,
  max_leverage: float = 1.0,
  leverage_conf_full: float = 0.82,
  high_conf_floor: float | None = None,
  target_return_pct: float = 10.0,
  min_or_pct: float = 0.003,
  use_hl_exits: bool | None = None,
  exit_at_session_end: bool = False,
  max_chase_attempts: int = 1,
  rank_by: str = "vol_score",
  bar_interval: str = "5m",
  open_range_bars: int | None = None,
  max_daily_loss_pct: float | None = None,
  max_trade_risk_pct: float | None = None,
  intraday_stop_with_session_end: bool | None = None,
  capital_use_frac: float = 1.0,
  min_or_edge_pct: float | None = None,
  require_bulk_confluence: bool = False,
  bulk_lookback_sessions: int = 3,
  bulk_min_win_rate: float = 0.55,
  bulk_min_n_trades: int = 2,
  bulk_min_deal_value: float = 25_000_000.0,
  exclude_tickers: list[str] | None = None,
  exclude_entities: list[str] | None = None,
  bulk_wr_prior: float = 0.55,
  bulk_wr_pseudo_n: float = 5.0,
  soft_trail_arm_pct: float | None = None,
  soft_trail_pct: float | None = None,
  bulk_second_min_wr: float | None = None,
  bulk_second_min_score_gap: float | None = None,
) -> dict[str, Any]:
  """Intraday ORB + adaptive gate on session bars; exits within session path.

  capital_use_frac: fraction of equity used as margin base per trade (≤1).
  Never deploys full book when < 1.0 — cash buffer stays untraded.
  min_or_edge_pct: sit out when best OR width < this (default cost+20bps in target_return).
  require_bulk_confluence: sit out ORB buys lacking NSE bulk BUY from high-WR investors.
  soft_trail_arm_pct / soft_trail_pct: under protect_only, arm trail after MFE ≥ arm,
    then exit when close gives back trail from peak (fraction, e.g. 0.015 / 0.01).
  bulk_second_min_wr / bulk_second_min_score_gap: only open 2nd copy-pro slot when
    top pick WR and score gap vs #2 clear both floors.
  """
  target_return_mode = filter_mode == "target_return"
  copy_bulk_mode = filter_mode == "copy_bulk_pro"
  capital_use_frac = max(0.05, min(1.0, float(capital_use_frac)))
  trail_arm = float(soft_trail_arm_pct) if soft_trail_arm_pct is not None else None
  trail_give = float(soft_trail_pct) if soft_trail_pct is not None else None
  if trail_arm is not None and trail_arm <= 0:
    trail_arm = None
  if trail_give is not None and trail_give <= 0:
    trail_give = None
  if trail_arm is None or trail_give is None:
    trail_arm = None
    trail_give = None
  sit_out_meta: dict[str, Any] | None = None
  exclude_tickers = list(exclude_tickers or [])
  exclude_entities = list(exclude_entities or [])
  relaxed = filter_mode in ("relaxed", "aggressive")
  orb_only = filter_mode == "orb_only" or target_return_mode or copy_bulk_mode
  if target_return_mode or copy_bulk_mode:
    # Allow multi-slot experiments when caller passes max_positions > 1.
    max_positions = max(1, int(max_positions))
    if use_hl_exits is None:
      # Guarded product: close-based stops (avoid 5m wick whipsaw)
      use_hl_exits = not bool(max_trade_risk_pct or max_daily_loss_pct)
    if intraday_stop_with_session_end is None:
      intraday_stop_with_session_end = bool(max_trade_risk_pct or max_daily_loss_pct)
  elif use_hl_exits is None:
    use_hl_exits = False
    if intraday_stop_with_session_end is None:
      intraday_stop_with_session_end = False
  elif intraday_stop_with_session_end is None:
    intraday_stop_with_session_end = False
  if relaxed:
    conf_floor = min(conf_floor, 0.58)
    max_positions = max(max_positions, 5)
  if filter_mode == "aggressive":
    conf_floor = min(conf_floor, 0.48)
    max_positions = max(max_positions, 6)
  if skip_peer_gate is None:
    skip_peer_gate = relaxed or orb_only or filter_mode == "aggressive"
  eff_peer = peer_target if peer_target is not None else (0.55 if relaxed else None)
  eff_min_fire = min_fire if min_fire is not None else (0.55 if relaxed else None)
  if target_return_mode:
    universe = IN_UNIVERSE_VOLATILE if market.upper() == "IN" else US_UNIVERSE_VOLATILE
    copy_picks = []
  elif copy_bulk_mode:
    from processor.smart_money_gate import rank_pro_buys

    ranked = rank_pro_buys(
      asof,
      market=market,
      lookback_sessions=max(1, int(bulk_lookback_sessions)),
      min_win_rate=float(bulk_min_win_rate),
      min_n_trades=int(bulk_min_n_trades),
      min_deal_value=float(bulk_min_deal_value),
      limit=max(8, max_positions * 3),
      universe=None,
      exclude_tickers=exclude_tickers,
      exclude_entities=exclude_entities,
      wr_prior=float(bulk_wr_prior),
      wr_pseudo_n=float(bulk_wr_pseudo_n),
    )
    copy_picks = ranked.get("picks") or []
    # Keep full ranked ladder so chase/alt fills when #1 has no bars.
    universe = [str(p["ticker"]) for p in copy_picks]
    if not universe:
      sit_out_meta = {
        "reason": "sit_out_no_pro_buys",
        "data_gap": bool(ranked.get("data_gap")),
        "error": ranked.get("error"),
      }
  else:
    copy_picks = []
    universe = IN_UNIVERSE if market.upper() == "IN" else US_UNIVERSE
  lev_cap = max(1.0, float(max_leverage))
  if copy_bulk_mode:
    lev_cap = min(lev_cap, 5.0)
  interval = pick_interval_for_date(asof, bar_interval)
  or_bars = open_range_bars if open_range_bars is not None else default_open_range_bars(interval)
  min_session_bars = or_bars + 2
  broker = PaperBroker(market.upper(), starting_cash=capital, currency=currency, leverage_max=lev_cap)
  cm = cost_model_for(market)
  cost = cm.round_trip_fraction
  ledger: list[dict[str, Any]] = []
  trades: list[dict[str, Any]] = []
  skipped: list[dict[str, Any]] = []
  used_fallback = False
  cash_start = capital

  ledger.append(
    {
      "ts": asof,
      "event": "session_open",
      "cash": round(cash_start, 2),
      "note": f"Session day sim · {market} · costs≈{cost*1e4:.1f}bps RT · filter={filter_mode} · max_lev={lev_cap:.1f}x · bars={interval}"
      + (
        f" · guard=daily{max_daily_loss_pct}%/trade{max_trade_risk_pct}%"
        if max_daily_loss_pct or max_trade_risk_pct
        else ""
      ),
    }
  )

  candidates: list[dict[str, Any]] = []
  for ticker in universe:
    bars = fetch_intraday_bars(ticker, session_date=asof, interval=interval, market=market)
    closes = session_closes(bars)
    if len(closes) < min_session_bars:
      skipped.append({"ticker": ticker, "reason": "insufficient_session_bars", "n": len(closes), "interval": interval})
      continue
    # Warm adaptive peers from daily history (no peek past asof)
    day = datetime.fromisoformat(asof).replace(tzinfo=timezone.utc)
    daily = _fetch_history(ticker, day)
    daily_closes = [px for _, px in daily]
    st = _state_for_ticker(ticker)
    if tp_override is not None:
      st.tp = tp_override
    if sl_override is not None:
      st.sl = sl_override
    if horizon_override is not None:
      st.horizon = horizon_override
    if filter_mode == "aggressive" and tp_override is None:
      st.tp = min(st.tp, 0.012)
      st.sl = min(st.sl, 0.006)
      st.horizon = min(st.horizon, 4)
    if target_return_mode and tp_override is None:
      st.sl = min(st.sl, 0.006)
      st.horizon = max(st.horizon, 12)
    if len(daily_closes) >= 80:
      _warm_peers(st, daily_closes, len(daily_closes) - 1, cost)
    highs = [float(b.get("high") or b["close"]) for b in bars]
    lows = [float(b.get("low") or b["close"]) for b in bars]
    if target_return_mode:
      sob = session_or_breakout(bars, open_range_bars=or_bars)
      or_w = float(sob.get("or_width_pct") or 0)
      if or_w < min_or_pct:
        skipped.append({"ticker": ticker, "reason": "or_too_narrow", "or_width_pct": or_w})
        continue
      entry_i = int(sob.get("entry_i") or 5)
      entry_px = float(sob.get("entry_px") or closes[min(entry_i, len(closes) - 1)])
      side = str(sob.get("side") or "flat")
      conf = float(sob.get("confidence") or 0.5)
      orb_reason = str(sob.get("reason") or "no_breakout")
      if tp_override is None:
        st.tp = max(min(or_w * 0.65, 0.03), 0.004)
      if sl_override is None:
        st.sl = max(min(or_w * 0.5, 0.025), 0.008)
        if max_daily_loss_pct and max_daily_loss_pct > 0:
          # Wider stop under guards so noise doesn't eat every entry
          st.sl = max(min(or_w * 0.55, 0.015), 0.008)
      orb = intraday_orb(closes, open_range_bars=or_bars, session_bars=closes)
    elif copy_bulk_mode:
      entry_i = min(or_bars, len(closes) - 1)
      entry_px = float(closes[entry_i])
      side = "buy"
      pick = next((p for p in copy_picks if str(p.get("ticker")) == ticker), None)
      raw_wr = float(pick["win_rate"]) if pick and pick.get("win_rate") is not None else 0.65
      conf = float(pick["win_rate_eff"]) if pick and pick.get("win_rate_eff") is not None else raw_wr
      conf = max(0.55, min(0.92, conf))
      orb_reason = "copy_bulk_pro"
      or_w = 0.0
      if tp_override is None:
        st.tp = 0.02
      if sl_override is None:
        st.sl = 0.01
      orb = intraday_orb(closes, open_range_bars=or_bars, session_bars=closes)
    else:
      # ORB on session + adaptive on daily context
      orb = intraday_orb(closes, open_range_bars=or_bars, session_bars=closes)
      # Entry at first breakout bar after open range
      entry_i = or_bars
      entry_px = closes[entry_i]
      for i in range(or_bars, len(closes)):
        sub = closes[: i + 1]
        sig_i = intraday_orb(sub, open_range_bars=or_bars, session_bars=sub)
        if sig_i.side == "buy":
          entry_i = i
          entry_px = closes[i]
          orb = sig_i
          break
      side = None  # set below
      conf = None
      orb_reason = None
    regime = market_regime(daily_closes) if len(daily_closes) >= 50 else "unknown"
    if regime_allow and regime not in regime_allow:
      skipped.append({"ticker": ticker, "reason": f"regime_blocked|{regime}", "allowed": regime_allow})
      continue
    if relaxed:
      st.effective_target = 0.55
      st.min_peers = max(3, st.min_peers // 2)
    adapt = (
      decide_from_state(
        daily_closes,
        st,
        buy_only=True,
        peer_target=eff_peer,
        min_fire=eff_min_fire,
        skip_peer_gate=bool(skip_peer_gate),
      )
      if len(daily_closes) >= 60 and not orb_only
      else None
    )
    gate_ok = adapt is not None and adapt.side == "buy" and "gate_ok" in (adapt.reason or "")
    if target_return_mode:
      conf = float(conf or 0.5)
      reason = f"target_return|or_w={or_w:.4f}|{orb_reason}|regime={regime}"
      side = "buy" if side == "buy" and conf >= conf_floor else "flat"
    elif copy_bulk_mode:
      reason = f"copy_bulk_pro|wr={conf:.3f}|{orb_reason}|regime={regime}"
      side = "buy"
    else:
      conf = float(orb.confidence if orb.side == "buy" else 0.5)
      if gate_ok and adapt:
        conf = max(conf, float(adapt.confidence))
      reason = f"session_orb|{orb.reason}|adapt={getattr(adapt, 'reason', None)}|regime={regime}"
      if orb_only and not target_return_mode:
        reason = f"orb_only|{reason}"
      elif relaxed:
        reason = f"relaxed|{reason}"
      elif filter_mode == "aggressive":
        reason = f"aggressive|{reason}"
      # Relaxed/orb_only: session ORB buy fires; strict: need adaptive gate_ok (or demo)
      side = "flat"
      if orb.side == "buy":
        if orb_only or relaxed or filter_mode == "aggressive" or gate_ok or allow_demo_fallback:
          side = "buy"
    if not target_return_mode and not copy_bulk_mode and orb.side == "buy" and not gate_ok and not relaxed and allow_demo_fallback:
      reason = f"setup_fallback|demo|{reason}"
      used_fallback = True
      conf = max(conf, conf_floor)
      side = "buy"
    pick_meta = None
    if copy_bulk_mode:
      pick_meta = next((p for p in copy_picks if str(p.get("ticker")) == ticker), None)
    candidates.append(
      {
        "ticker": ticker,
        "asof_bar": asof,
        "price": round(entry_px, 4),
        "side": side,
        "confidence": round(conf, 4),
        "reason": reason,
        "tp": st.tp,
        "sl": st.sl,
        "horizon": min(st.horizon, max(3, len(closes) - entry_i - 1)),
        "closes_m": closes,
        "highs_m": highs,
        "lows_m": lows,
        "use_hl_exits": use_hl_exits,
        "idx_m": entry_i,
        "dates_m": [b.get("ts") or asof for b in bars],
        "is_demo_fallback": "setup_fallback" in reason,
        "is_relaxed": (relaxed or orb_only or filter_mode == "aggressive" or target_return_mode or copy_bulk_mode)
        and side == "buy"
        and not ("setup_fallback" in reason),
        "regime": regime,
        "vol_score": float(sob.get("score") or 0) if target_return_mode else conf,
        "or_width_pct": float(or_w) if target_return_mode else 0.0,
        "bulk_score": float(pick_meta.get("score") or 0) if pick_meta else 0.0,
        "bulk_wr": float(
          pick_meta.get("win_rate_eff")
          or pick_meta.get("win_rate")
          or pick_meta.get("wr")
          or 0
        )
        if pick_meta
        else 0.0,
        "bulk_entity": (pick_meta.get("entity_normalized") if pick_meta else None),
      }
    )

  if target_return_mode:
    buys = [c for c in candidates if c["side"] == "buy"]
    if rank_by == "or_width":
      buys.sort(key=lambda x: float(x.get("or_width_pct") or 0), reverse=True)
    else:
      buys.sort(key=lambda x: x.get("vol_score", 0), reverse=True)
    chase_n = max(1, int(max_chase_attempts))
    # Take enough candidates for chase OR parallel slots (whichever needs more).
    buys = buys[: max(chase_n, max_positions)]
    # Preserve OR-width / vol_score order — do NOT re-rank by confidence (that
    # used to destroy chase and pick high-conf fade names over widest OR).
    if high_conf_floor is not None:
      buys = [c for c in buys if c["confidence"] >= high_conf_floor]
    # Sit out when best OR width cannot clear round-trip cost + buffer.
    # Only for guarded product (or explicit min_or_edge_pct). Raw research keeps always-on.
    if min_or_edge_pct is not None:
      min_or_edge = float(min_or_edge_pct)
    elif max_trade_risk_pct or max_daily_loss_pct:
      min_or_edge = cost + 0.002
    else:
      min_or_edge = 0.0
    if buys and min_or_edge > 0:
      best_or = float(buys[0].get("or_width_pct") or 0)
      if best_or < min_or_edge:
        sit_out_meta = {
          "reason": "sit_out_or_edge_below_cost",
          "or_width_pct": round(best_or, 6),
          "min_or_edge_pct": round(min_or_edge, 6),
        }
        buys = []
  elif copy_bulk_mode:
    buys = [c for c in candidates if c["side"] == "buy"]
    # Preserve ranker score order (not raw WR) so shrunk scores stick.
    buys.sort(key=lambda x: float(x.get("bulk_score") or x.get("confidence") or 0), reverse=True)
    if (
      max_positions >= 2
      and bulk_second_min_wr is not None
      and bulk_second_min_score_gap is not None
      and len(buys) >= 2
    ):
      top_wr = float(buys[0].get("bulk_wr") or buys[0].get("confidence") or 0)
      gap = float(buys[0].get("bulk_score") or 0) - float(buys[1].get("bulk_score") or 0)
      if top_wr >= float(bulk_second_min_wr) and gap >= float(bulk_second_min_score_gap):
        buys = buys[:2]
      else:
        buys = buys[:1]
    else:
      buys = buys[:max_positions]
    if not buys and sit_out_meta is None:
      sit_out_meta = {"reason": "sit_out_no_pro_buys"}
  elif relaxed or orb_only or filter_mode == "aggressive":
    buys = [
      c
      for c in candidates
      if c["side"] == "buy" and c["confidence"] >= conf_floor and c.get("is_relaxed")
    ]
    buys.sort(key=lambda x: x["confidence"], reverse=True)
    if high_conf_floor is not None:
      buys = [c for c in buys if c["confidence"] >= high_conf_floor]
    buys = buys[:max_positions]
  else:
    buys = [
      c
      for c in candidates
      if c["side"] == "buy"
      and c["confidence"] >= conf_floor
      and ("gate_ok" in (c["reason"] or "") or c.get("is_demo_fallback"))
    ]
    buys = [c for c in buys if (not c.get("is_demo_fallback")) or allow_demo_fallback]
    real = [c for c in buys if not c.get("is_demo_fallback")]
    buys = (real or buys)[:max_positions]
    buys.sort(key=lambda x: x["confidence"], reverse=True)
    if high_conf_floor is not None:
      buys = [c for c in buys if c["confidence"] >= high_conf_floor]
    buys = buys[:max_positions]

  # Lane A: ORB must also have smart-money bulk BUY confirmation.
  if require_bulk_confluence and buys:
    from processor.smart_money_gate import ticker_has_pro_buy

    kept: list[dict[str, Any]] = []
    for c in buys:
      gate = ticker_has_pro_buy(
        str(c["ticker"]),
        asof,
        market=market,
        lookback_sessions=max(1, int(bulk_lookback_sessions)),
        min_win_rate=float(bulk_min_win_rate),
      )
      if gate.get("passes"):
        kept.append({**c, "bulk_gate": gate})
      else:
        skipped.append(
          {
            "ticker": c["ticker"],
            "reason": "sit_out_no_bulk_confluence",
            "confidence": c.get("confidence"),
            "side": c.get("side"),
            "price": c.get("price"),
            "deals": (gate.get("deals") or [])[:2],
          }
        )
    if not kept:
      sit_out_meta = {
        "reason": "sit_out_no_bulk_confluence",
        "n_candidates": len(buys),
      }
    buys = kept

  for c in candidates:
    if c not in buys:
      reason = c["reason"] if c["side"] != "buy" else "not_selected_or_below_conf"
      if sit_out_meta is not None and c["side"] == "buy":
        reason = str(sit_out_meta.get("reason") or reason)
      row = {
        "ticker": c["ticker"],
        "reason": reason,
        "confidence": c["confidence"],
        "side": c["side"],
        "price": c["price"],
      }
      if sit_out_meta is not None and c["side"] == "buy":
        for k in ("or_width_pct", "min_or_edge_pct", "n_candidates", "data_gap"):
          if k in sit_out_meta:
            row[k] = sit_out_meta[k]
      skipped.append(row)

  # Margin base = fraction of equity only (capital_use_frac < 1 keeps cash untraded).
  per_slot_base = (capital * capital_use_frac) / max(1, max_positions)
  for c in buys:
    flat_eq = max(broker.cash - broker.borrowed, 1.0)
    if max_daily_loss_pct and daily_loss_halted(flat_eq, cash_start, max_daily_loss_pct):
      skipped.append(
        {
          "reason": "daily_loss_halt",
          "session_return_pct": round(session_return_pct(flat_eq, cash_start), 3),
          "max_daily_loss_pct": max_daily_loss_pct,
        }
      )
      break
    if target_return_mode and max_chase_attempts > 1:
      ret_so_far = (flat_eq - cash_start) / cash_start
      if ret_so_far * 100.0 >= target_return_pct:
        break
      need_frac = max(0.005, target_return_pct / 100.0 - ret_so_far)
      if exit_at_session_end:
        exp = max(float(c.get("or_width_pct") or 0), c["tp"], 0.004)
        lev = leverage_for_target(need_frac, exp, max_leverage=lev_cap)
      else:
        lev = leverage_for_target(need_frac, c["tp"], max_leverage=lev_cap)
      per_slot = flat_eq * capital_use_frac
    elif target_return_mode:
      if exit_at_session_end:
        exp = max(float(c.get("or_width_pct") or 0), c["tp"], 0.004)
        lev = leverage_for_target(target_return_pct / 100.0, exp, max_leverage=lev_cap)
      else:
        lev = leverage_for_target(target_return_pct / 100.0, c["tp"], max_leverage=lev_cap)
      per_slot = per_slot_base
    else:
      lev = confidence_leverage(
        c["confidence"],
        max_leverage=lev_cap,
        conf_floor=conf_floor,
        conf_full=leverage_conf_full,
      )
      per_slot = per_slot_base
    if max_trade_risk_pct or max_daily_loss_pct:
      lev, guard_notes = apply_session_guards(
        lev,
        sl_frac=float(c["sl"]),
        equity=flat_eq,
        cash_start=cash_start,
        max_trade_risk_pct=max_trade_risk_pct,
        max_daily_loss_pct=max_daily_loss_pct,
      )
      # Never exceed target-return sizing when guards only tighten tail
      if guard_notes:
        c = {**c, "guard_notes": guard_notes}
    notional = per_slot * lev
    notional = min(notional, broker.buying_power() * 0.98)
    if lev_cap <= 1.0:
      notional = min(notional, broker.cash * 0.98)
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
    fee_in = cm.fee_on_notional(entry_notional, sides=1)
    broker.charge_fee(fee_in)
    fee = float(fill.fee or 0) + fee_in
    trade_id = fill.broker_order_id or f"sim-{c['ticker']}"
    ledger.append(
      {
        "ts": c["dates_m"][c["idx_m"]] if c["idx_m"] < len(c["dates_m"]) else asof,
        "event": "buy",
        "trade_id": trade_id,
        "ticker": c["ticker"],
        "qty": fill.fill_qty,
        "price": fill.fill_price,
        "notional": entry_notional,
        "fee": fee,
        "cash_after": round(broker.cash, 2),
        "confidence": c["confidence"],
        "strategy": "session_orb+adaptive",
        "signal_reason": c["reason"],
        "is_demo_fallback": c.get("is_demo_fallback"),
        "leverage": lev,
        "guard_notes": c.get("guard_notes"),
      }
    )
    # Path exit on session bars
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
    exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
    exit_reason = "session_horizon"
    entry = c["closes_m"][c["idx_m"]]
    session_end_only = (
      (target_return_mode or copy_bulk_mode)
      and exit_at_session_end
      and not intraday_stop_with_session_end
    )
    if session_end_only:
      exit_idx = len(c["closes_m"]) - 1
      exit_px = c["closes_m"][exit_idx]
      exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
      exit_reason = "session_close"
    else:
      highs_m = c.get("highs_m") or c["closes_m"]
      lows_m = c.get("lows_m") or c["closes_m"]
      hl = bool(c.get("use_hl_exits"))
      # Product mode: cut losers on SL, let winners run to session close.
      protect_only = bool(
        (target_return_mode or copy_bulk_mode)
        and exit_at_session_end
        and intraday_stop_with_session_end
      )
      scan_bars = c["horizon"]
      if protect_only:
        scan_bars = max(c["horizon"], len(c["closes_m"]) - c["idx_m"] - 1)
      peak_r = 0.0
      trail_armed = False
      for j in range(1, scan_bars + 1):
        if c["idx_m"] + j >= len(c["closes_m"]):
          break
        bar_i = c["idx_m"] + j
        if hl:
          r_hi = highs_m[bar_i] / entry - 1.0
          r_lo = lows_m[bar_i] / entry - 1.0
          if (not protect_only) and r_hi >= c["tp"]:
            exit_idx = bar_i
            exit_px = entry * (1.0 + c["tp"])
            exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
            exit_reason = "take_profit"
            break
          if r_lo <= -c["sl"]:
            exit_idx = bar_i
            exit_px = entry * (1.0 - c["sl"])
            exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
            exit_reason = "stop_loss"
            break
          if protect_only and trail_arm is not None and trail_give is not None:
            peak_r = max(peak_r, r_hi)
            if peak_r >= trail_arm:
              trail_armed = True
            r_close = c["closes_m"][bar_i] / entry - 1.0
            if trail_armed and r_close <= peak_r - trail_give:
              exit_idx = bar_i
              exit_px = c["closes_m"][bar_i]
              exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
              exit_reason = "soft_trail"
              break
        r = c["closes_m"][bar_i] / entry - 1.0
        if (not protect_only) and r >= c["tp"]:
          exit_idx = bar_i
          exit_px = c["closes_m"][exit_idx]
          exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
          exit_reason = "take_profit"
          break
        if r <= -c["sl"]:
          exit_idx = bar_i
          exit_px = c["closes_m"][exit_idx]
          exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
          exit_reason = "stop_loss"
          break
        if (not hl) and protect_only and trail_arm is not None and trail_give is not None:
          peak_r = max(peak_r, r)
          if peak_r >= trail_arm:
            trail_armed = True
          if trail_armed and r <= peak_r - trail_give:
            exit_idx = bar_i
            exit_px = c["closes_m"][bar_i]
            exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
            exit_reason = "soft_trail"
            break
      if protect_only and exit_reason == "session_horizon":
        exit_idx = len(c["closes_m"]) - 1
        exit_px = c["closes_m"][exit_idx]
        exit_ts = c["dates_m"][exit_idx] if exit_idx < len(c["dates_m"]) else asof
        exit_reason = "session_close"
    if out is None and exit_reason == "session_horizon":
      pass

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
    fee_out = cm.fee_on_notional(exit_notional, sides=1)
    broker.charge_fee(fee_out)
    sell_fee = float(sell.fee or 0) + fee_out
    pnl = round(exit_notional - entry_notional - fee - sell_fee, 2)
    pnl_pct = round(100.0 * pnl / entry_notional, 3) if entry_notional else 0.0
    ledger.append(
      {
        "ts": exit_ts,
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
        "entry_date": asof if not c.get("dates_m") else str(c["dates_m"][c["idx_m"]])[:19],
        "exit_date": str(exit_ts)[:19],
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
        "strategy_id": "session_orb",
        "signal_reason": c["reason"],
        "is_demo_fallback": bool(c.get("is_demo_fallback")),
        "leverage": round(float(lev), 4),
        "money_put": entry_notional,
        "money_returned": exit_notional,
        "or_width_pct": round(float(c.get("or_width_pct") or 0), 6),
        "vol_score": round(float(c.get("vol_score") or 0), 4),
        "tp_frac": float(c.get("tp") or 0),
        "sl_frac": float(c.get("sl") or 0),
        "tp_pct": round(100.0 * float(c.get("tp") or 0), 4),
        "sl_pct": round(100.0 * float(c.get("sl") or 0), 4),
        "slot_capital": round(float(per_slot), 2),
        "target_notional": round(float(notional), 2),
        "buying_power_at_entry": round(float(broker.buying_power() + entry_notional), 2),
        "guard_notes": c.get("guard_notes"),
        "entry_bar_i": c.get("idx_m"),
        "exit_bar_i": exit_idx,
        "horizon_bars": c.get("horizon"),
        "rank_key": "or_width" if float(c.get("or_width_pct") or 0) else "confidence",
        "bulk_entity": c.get("bulk_entity"),
        "bulk_score": c.get("bulk_score"),
      }
    )

  realized = round(sum(t["pnl"] for t in trades), 2)
  # Book capital must equal start + sum(trade PnL). Broker.cash previously omitted CostModel
  # India fees (~30bps RT) while trade.pnl included them — that inflated oneshot equity paths.
  cash_end = round(cash_start + realized, 2)
  broker.cash = cash_end
  broker.borrowed = 0.0
  broker.positions.clear()
  edge_ok = bool(trades) and not any(t.get("is_demo_fallback") for t in trades) and not used_fallback
  if (relaxed or orb_only or filter_mode == "aggressive" or target_return_mode) and trades:
    edge_ok = True
  return _pack_result(
    mode="paper_session_sim",
    asof=asof,
    market=market,
    currency=currency,
    cash_start=cash_start,
    cash_end=cash_end,
    realized=realized,
    trades=trades,
    ledger=ledger,
    skipped=skipped,
    edge_metrics_valid=edge_ok,
    used_demo_fallback=used_fallback or any(t.get("is_demo_fallback") for t in trades),
    cost_bps_rt=round(cost * 1e4, 2),
    filter_mode=filter_mode,
    max_leverage=lev_cap,
    capital_use_frac=capital_use_frac,
  )


def _pack_result(
  *,
  mode: str,
  asof: str,
  market: str,
  currency: str,
  cash_start: float,
  cash_end: float,
  realized: float,
  trades: list,
  ledger: list,
  skipped: list,
  edge_metrics_valid: bool,
  used_demo_fallback: bool,
  cost_bps_rt: float,
  filter_mode: str = "strict",
  max_leverage: float = 1.0,
  capital_use_frac: float = 1.0,
) -> dict[str, Any]:
  hit = None
  if trades:
    # Edge hit rate excludes demo fallback fills
    edge_trades = [t for t in trades if not t.get("is_demo_fallback")]
    src = edge_trades if edge_metrics_valid else []
    if src:
      hit = round(100.0 * sum(1 for t in src if t["pnl"] > 0) / len(src), 2)
  ledger.append(
    {
      "ts": asof,
      "event": "session_summary",
      "cash": cash_end,
      "realized_pnl": realized,
      "n_trades": len(trades),
      "edge_metrics_valid": edge_metrics_valid,
      "return_pct": round(100.0 * (cash_end - cash_start) / cash_start, 3) if cash_start else 0,
    }
  )
  return {
    "mode": mode,
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
    "edge_metrics_valid": edge_metrics_valid,
    "used_demo_fallback": used_demo_fallback,
    "demo_badge": "DEMO — setup_fallback; not edge" if used_demo_fallback else None,
    "filter_mode": filter_mode,
    "max_leverage": max_leverage,
    "capital_use_frac": capital_use_frac,
    "cost_bps_rt": cost_bps_rt,
    "pnl_statement": {
      "opening_cash": cash_start,
      "closing_cash": cash_end,
      "gross_pnl": realized,
      "fees_total": round(sum(t["fees"] for t in trades), 4),
      "wins": sum(1 for t in trades if t["pnl"] > 0),
      "losses": sum(1 for t in trades if t["pnl"] <= 0),
      "hit_rate_pct": hit if edge_metrics_valid else None,
      "hit_rate_includes_demo": False,
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
          "is_demo_fallback": t.get("is_demo_fallback"),
        }
        for t in trades
      ],
    },
    "disclaimer": (
      "Paper simulation — not live broker fills; not investment advice. "
      + ("DEMO fallback fills are excluded from edge hit rate. " if used_demo_fallback else "")
      + ("Session path with modeled costs. " if "session" in mode else "Daily-bar path — not session fills. ")
    ),
  }


def simulate_day(
  *,
  asof: str = "2024-08-23",
  capital: float = 10_000.0,
  currency: str = "INR",
  market: str = "IN",
  max_positions: int = 3,
  conf_floor: float = 0.70,
  path_mode: str = "session",
  allow_demo_fallback: bool = False,
  filter_mode: str = "strict",
  tp_override: float | None = None,
  sl_override: float | None = None,
  horizon_override: int | None = None,
  peer_target: float | None = None,
  min_fire: float | None = None,
  skip_peer_gate: bool | None = None,
  regime_allow: list[str] | None = None,
  max_leverage: float = 1.0,
  leverage_conf_full: float = 0.82,
  high_conf_floor: float | None = None,
  target_return_pct: float = 10.0,
  min_or_pct: float = 0.003,
  use_hl_exits: bool | None = None,
  exit_at_session_end: bool = False,
  max_chase_attempts: int = 1,
  rank_by: str = "vol_score",
  bar_interval: str = "5m",
  open_range_bars: int | None = None,
  max_daily_loss_pct: float | None = None,
  max_trade_risk_pct: float | None = None,
  intraday_stop_with_session_end: bool | None = None,
  capital_use_frac: float = 1.0,
  min_or_edge_pct: float | None = None,
  require_bulk_confluence: bool = False,
  bulk_lookback_sessions: int = 3,
  bulk_min_win_rate: float = 0.55,
  bulk_min_n_trades: int = 2,
  bulk_min_deal_value: float = 25_000_000.0,
  exclude_tickers: list[str] | None = None,
  exclude_entities: list[str] | None = None,
  bulk_wr_prior: float = 0.55,
  bulk_wr_pseudo_n: float = 5.0,
  soft_trail_arm_pct: float | None = None,
  soft_trail_pct: float | None = None,
  bulk_second_min_wr: float | None = None,
  bulk_second_min_score_gap: float | None = None,
) -> dict[str, Any]:
  """Replay paper book for one calendar day with full ledger.

  path_mode: session (default, Stage A) | daily (legacy research)
  filter_mode: strict | relaxed | orb_only | aggressive | target_return | copy_bulk_pro
  max_leverage: sim-only margin cap (confidence-scaled sizing below cap)
  target_return_pct: when filter_mode=target_return, size leverage to this daily return on TP hit
  max_daily_loss_pct / max_trade_risk_pct: session guardrails (halt day / cap per-trade lev)
  capital_use_frac: fraction of equity used as margin base (≤1 keeps cash untraded)
  min_or_edge_pct: sit out when best OR width below this (target_return; default cost+20bps)
  require_bulk_confluence: ORB only if NSE bulk BUY from high-WR investor (Lane A)
  soft_trail_arm_pct / soft_trail_pct: protect_only soft trail (fractions)
  bulk_second_min_wr / bulk_second_min_score_gap: selective 2nd copy-pro slot
  allow_demo_fallback: if True, may fill via setup_fallback but marks demo / invalidates edge metrics
  """
  if path_mode == "session":
    return _simulate_session_day(
      asof=asof,
      capital=capital,
      currency=currency,
      market=market,
      max_positions=max_positions,
      conf_floor=conf_floor,
      allow_demo_fallback=allow_demo_fallback,
      filter_mode=filter_mode,
      tp_override=tp_override,
      sl_override=sl_override,
      horizon_override=horizon_override,
      peer_target=peer_target,
      min_fire=min_fire,
      skip_peer_gate=skip_peer_gate,
      regime_allow=regime_allow,
      max_leverage=max_leverage,
      leverage_conf_full=leverage_conf_full,
      high_conf_floor=high_conf_floor,
      target_return_pct=target_return_pct,
      min_or_pct=min_or_pct,
      use_hl_exits=use_hl_exits,
      exit_at_session_end=exit_at_session_end,
      max_chase_attempts=max_chase_attempts,
      rank_by=rank_by,
      bar_interval=bar_interval,
      open_range_bars=open_range_bars,
      max_daily_loss_pct=max_daily_loss_pct,
      max_trade_risk_pct=max_trade_risk_pct,
      intraday_stop_with_session_end=intraday_stop_with_session_end,
      capital_use_frac=capital_use_frac,
      min_or_edge_pct=min_or_edge_pct,
      require_bulk_confluence=require_bulk_confluence,
      bulk_lookback_sessions=bulk_lookback_sessions,
      bulk_min_win_rate=bulk_min_win_rate,
      bulk_min_n_trades=bulk_min_n_trades,
      bulk_min_deal_value=bulk_min_deal_value,
      exclude_tickers=exclude_tickers,
      exclude_entities=exclude_entities,
      bulk_wr_prior=bulk_wr_prior,
      bulk_wr_pseudo_n=bulk_wr_pseudo_n,
      soft_trail_arm_pct=soft_trail_arm_pct,
      soft_trail_pct=soft_trail_pct,
      bulk_second_min_wr=bulk_second_min_wr,
      bulk_second_min_score_gap=bulk_second_min_score_gap,
    )

  day = datetime.fromisoformat(asof).replace(tzinfo=timezone.utc)
  universe = IN_UNIVERSE if market.upper() == "IN" else US_UNIVERSE
  broker = PaperBroker(market.upper(), starting_cash=capital, currency=currency)
  cost = cost_fraction(market)

  ledger: list[dict[str, Any]] = []
  trades: list[dict[str, Any]] = []
  skipped: list[dict[str, Any]] = []
  cash_start = capital
  used_fallback = False

  ledger.append(
    {
      "ts": asof,
      "event": "session_open",
      "cash": round(cash_start, 2),
      "note": f"Daily-bar paper day sim · {market} · {currency} {capital:,.0f}",
    }
  )

  candidates: list[dict[str, Any]] = []

  for ticker in universe:
    bars = _fetch_history(ticker, day)
    if len(bars) < 80:
      skipped.append({"ticker": ticker, "reason": "insufficient_history", "n": len(bars)})
      continue
    dates = [d for d, _ in bars]
    if asof not in dates:
      prior = [d for d in dates if d <= asof]
      if not prior:
        skipped.append({"ticker": ticker, "reason": "no_bar_on_or_before_asof"})
        continue
      asof_bar = prior[-1]
    else:
      asof_bar = asof
    idx = dates.index(asof_bar)
    closes = [px for _, px in bars]
    future = _fetch_history(ticker, day + timedelta(days=40), lookback_days=60)
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
        "is_demo_fallback": False,
        "regime": market_regime(window),
      }
    )

  buys = [c for c in candidates if c["side"] == "buy" and c["confidence"] >= conf_floor and "gate_ok" in (c["reason"] or "")]
  if not buys and allow_demo_fallback:
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
      c["is_demo_fallback"] = True
      used_fallback = True
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
  cm = cost_model_for(market)

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
    fee_in = cm.fee_on_notional(entry_notional, sides=1)
    broker.charge_fee(fee_in)
    fee = float(fill.fee or 0) + fee_in
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
        "is_demo_fallback": c.get("is_demo_fallback"),
        "tp_pct": round(c["tp"] * 100, 2),
        "sl_pct": round(c["sl"] * 100, 2),
        "horizon_bars": c["horizon"],
      }
    )

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
    fee_out = cm.fee_on_notional(exit_notional, sides=1)
    broker.charge_fee(fee_out)
    sell_fee = float(sell.fee or 0) + fee_out
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
        "is_demo_fallback": bool(c.get("is_demo_fallback")),
        "tp_pct": round(c["tp"] * 100, 2),
        "sl_pct": round(c["sl"] * 100, 2),
        "money_put": entry_notional,
        "money_returned": exit_notional,
      }
    )

  realized = round(sum(t["pnl"] for t in trades), 2)
  cash_end = round(cash_start + realized, 2)
  broker.cash = cash_end
  broker.borrowed = 0.0
  broker.positions.clear()
  edge_ok = bool(trades) and not used_fallback and not any(t.get("is_demo_fallback") for t in trades)
  return _pack_result(
    mode="paper_day_sim",
    asof=asof,
    market=market,
    currency=currency,
    cash_start=cash_start,
    cash_end=cash_end,
    realized=realized,
    trades=trades,
    ledger=ledger,
    skipped=skipped,
    edge_metrics_valid=edge_ok,
    used_demo_fallback=used_fallback,
    cost_bps_rt=round(cost * 1e4, 2),
  )
