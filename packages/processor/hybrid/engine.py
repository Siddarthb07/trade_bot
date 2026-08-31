"""Hybrid session / window simulator."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from processor.benchmarks import compare_to_benchmarks, primary_score
from processor.day_sim import simulate_day
from processor.hybrid.chooser import choose_strategy
from processor.hybrid.ledger import load_chooser_state, record_session_outcomes
from processor.hybrid.registry import sim_kwargs_for_strategy
from processor.hybrid.rules_ledger import (
  learn_from_session,
  merge_excludes,
  read_daily_briefing,
)
from processor.hybrid.ticker_chooser import rank_tickers
from processor.hybrid.wins import detect_wins_from_run, list_wins
from processor.intraday_bars import fetch_intraday_bars, pick_interval_for_date
from processor.strategies import market_regime


def _sessions(start: str, end: str) -> list[str]:
  sd, ed = date.fromisoformat(start), date.fromisoformat(end)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def _infer_regime(asof: str, market: str = "IN") -> str:
  # Light regime hint from NIFTY/SPY-ish proxy via first liquid ticker daily path is heavy;
  # default unknown — chooser still works. Optional: use RELIANCE closes if cheap.
  try:
    from processor.day_sim import _fetch_history

    day = date.fromisoformat(asof)
    ticker = "RELIANCE.NS" if market.upper() == "IN" else "SPY"
    # _fetch_history expects datetime
    from datetime import datetime, timezone

    hist = _fetch_history(ticker, datetime.fromisoformat(asof).replace(tzinfo=timezone.utc))
    closes = [px for _, px in hist]
    if len(closes) >= 50:
      return market_regime(closes)
  except Exception:
    pass
  return "unknown"


def simulate_hybrid_day(
  *,
  asof: str,
  capital: float = 10_000.0,
  market: str = "IN",
  lane: str = "product",
  force_strategy: str | None = None,
  include_ticker_ranks: bool = True,
  include_bars: bool = True,
  record_learning: bool = True,
  max_positions: int | None = None,
  bar_interval: str = "5m",
  exclude_tickers: list[str] | None = None,
  exclude_entities: list[str] | None = None,
) -> dict[str, Any]:
  """Run one hybrid session day with chooser + risk-mapped strategy."""
  lane = (lane or "product").strip().lower()
  if lane not in ("product", "stretch", "research"):
    return {"error": "lane must be product|stretch|research"}

  # Self-learning loop: ALWAYS read rules ledger before ranking/sizing.
  briefing = read_daily_briefing(asof, mark_read=True)
  ex_t, ex_e, sitout = merge_excludes(
    briefing, exclude_tickers=exclude_tickers, exclude_entities=exclude_entities
  )
  if sitout:
    return {
      "mode": "hybrid_session",
      "asof": asof,
      "lane": lane,
      "strategy_id": force_strategy or "sitout",
      "return_pct": 0.0,
      "capital_start": capital,
      "capital_end": capital,
      "n_trades": 0,
      "trades": [],
      "sitout": True,
      "rules_briefing": briefing,
      "chooser": {"picked": "sitout", "reason": "rules_ledger_sitout"},
      "disclaimer": "Sit-out from rules ledger — no trade this session.",
    }

  state = load_chooser_state()
  regime = _infer_regime(asof, market)
  chooser = choose_strategy(
    lane=lane,
    regime=regime,
    chooser_state=state,
    force_strategy=force_strategy,
  )
  strategy_id = str(chooser["picked"])
  kwargs = sim_kwargs_for_strategy(strategy_id, lane)
  kwargs.pop("bar_interval", None)
  # Engine owns slot count; strategy kwargs must not double-pass it.
  strategy_slots = int(kwargs.pop("max_positions", 1) or 1)
  sl_cd = int(kwargs.pop("sl_cooldown_days", 0) or 0)
  ent_cd = int(kwargs.pop("entity_cooldown_days", 0) or 0)
  sit_cd = int(kwargs.pop("sitout_after_sl_days", 0) or 0)
  slots = int(max_positions) if max_positions is not None else strategy_slots
  slots = max(1, min(slots, 8))
  if ex_t:
    kwargs["exclude_tickers"] = list(ex_t)
  if ex_e:
    kwargs["exclude_entities"] = list(ex_e)

  currency = "INR" if market.upper() == "IN" else "USD"
  sim = simulate_day(
    asof=asof,
    capital=capital,
    currency=currency,
    market=market.upper(),
    path_mode="session",
    max_positions=slots,
    allow_demo_fallback=False,
    **kwargs,
  )

  trades = list(sim.get("trades") or [])
  ticker_ranks: list[dict[str, Any]] = []
  if include_ticker_ranks:
    try:
      ticker_ranks = rank_tickers(
        asof=asof,
        market=market,
        strategy_id=strategy_id,
        conf_floor=float(kwargs.get("conf_floor") or 0.48),
        min_or_pct=float(kwargs.get("min_or_pct") or 0.0015),
        bar_interval=bar_interval,
        top_n=24,
      )
    except Exception as e:  # noqa: BLE001
      ticker_ranks = [{"error": str(e)}]

  rank_by = {str(r.get("ticker")): r for r in ticker_ranks if isinstance(r, dict) and r.get("ticker")}
  for i, t in enumerate(trades, 1):
    tk = str(t.get("ticker") or "")
    rr = rank_by.get(tk) or {}
    t["pick_order"] = i
    t["hybrid_strategy_id"] = strategy_id
    t["lane"] = lane
    t["regime"] = regime
    t["universe_rank"] = rr.get("rank")
    t["universe_score"] = rr.get("score")
    t["why_selected"] = (
      f"#{i} pick | strategy={strategy_id} ({chooser.get('reason')}) | "
      f"conf={t.get('confidence')} | or_width={t.get('or_width_pct')} | "
      f"signal={t.get('signal_reason')} | money_put={t.get('money_put')} | "
      f"lev={t.get('leverage')}x | universe_rank={rr.get('rank')} | "
      f"score={rr.get('score')}"
    )
    t["decision"] = {
      "chooser": chooser,
      "sim_kwargs": {k: v for k, v in kwargs.items()},
      "max_positions": slots,
      "rank_row": rr,
      "money": {
        "put": t.get("money_put"),
        "returned": t.get("money_returned"),
        "pnl": t.get("pnl"),
        "fees": t.get("fees"),
        "slot_capital": t.get("slot_capital"),
        "target_notional": t.get("target_notional"),
        "leverage": t.get("leverage"),
      },
      "signal": {
        "confidence": t.get("confidence"),
        "or_width_pct": t.get("or_width_pct"),
        "or_width_bps": round(float(t.get("or_width_pct") or 0) * 1e4, 2),
        "reason": t.get("signal_reason"),
        "tp_pct": t.get("tp_pct"),
        "sl_pct": t.get("sl_pct"),
        "vol_score": t.get("vol_score"),
      },
    }

  # Attach bars for each trade (prefer finer interval)
  if include_bars and trades:
    for t0 in trades:
      ticker = str(t0.get("ticker") or "")
      if not ticker:
        continue
      try:
        interval = pick_interval_for_date(asof, bar_interval)
        bars = fetch_intraday_bars(ticker, session_date=asof, interval=interval, market=market)
        if len(bars) < 10 and bar_interval == "1m":
          interval = pick_interval_for_date(asof, "5m")
          bars = fetch_intraday_bars(ticker, session_date=asof, interval=interval, market=market)
        t0["bar_interval"] = interval
        t0["n_bars"] = len(bars)
        t0["bars"] = [
          {
            "ts": b.get("ts"),
            "open": b.get("open"),
            "high": b.get("high"),
            "low": b.get("low"),
            "close": b.get("close"),
            "volume": b.get("volume"),
          }
          for b in bars
        ]
        t0["markers"] = [
          {"side": "buy", "price": t0.get("entry_price"), "ts": t0.get("entry_date")},
          {"side": "sell", "price": t0.get("exit_price"), "ts": t0.get("exit_date")},
        ]
      except Exception as e:  # noqa: BLE001
        t0["bars_error"] = str(e)

  ret = float(sim.get("return_pct") or 0)
  rules_learn = None
  if record_learning:
    record_session_outcomes(
      asof=asof,
      lane=lane,
      strategy_id=strategy_id,
      regime=regime,
      session_return_pct=ret,
      trades=trades,
      chooser=chooser,
      sim_kwargs=kwargs,
      ticker_ranks=ticker_ranks,
    )
    rules_learn = learn_from_session(
      asof=asof,
      trades=trades,
      session_return_pct=ret,
      strategy_id=strategy_id,
      ticker_cooldown_sessions=max(1, sl_cd or 2),
      entity_cooldown_sessions=max(0, ent_cd),
    )

  score = primary_score(compound_pct=ret, worst_day_pct=ret, max_dd_pct=abs(min(0.0, ret)))
  money_put_total = round(sum(float(t.get("money_put") or 0) for t in trades), 2)
  money_back_total = round(sum(float(t.get("money_returned") or 0) for t in trades), 2)
  picked = [r for r in ticker_ranks if isinstance(r, dict) and r.get("eligible")]
  rejected = [r for r in ticker_ranks if isinstance(r, dict) and r.get("eligible") is False]

  return {
    "mode": "hybrid_session",
    "north_star": "most_profits",
    "asof": asof,
    "lane": lane,
    "regime": regime,
    "chooser": chooser,
    "strategy_id": strategy_id,
    "sim_kwargs": {k: v for k, v in kwargs.items() if k not in ("bar_interval",)},
    "max_positions": slots,
    "bar_interval": bar_interval,
    "ticker_ranks": ticker_ranks,
    "universe_ladder": ticker_ranks,
    "eligible_candidates": picked,
    "rejected_candidates": rejected,
    "capital_start": sim.get("capital_start"),
    "capital_end": sim.get("capital_end"),
    "realized_pnl": sim.get("realized_pnl"),
    "return_pct": ret,
    "primary_score": score,
    "n_trades": sim.get("n_trades"),
    "money_put_total": money_put_total,
    "money_returned_total": money_back_total,
    "trades": trades,
    "rules_briefing": briefing,
    "rules_learn": rules_learn,
    "copy_pro_cooldown_cfg": {
      "sl_cooldown_days": sl_cd,
      "entity_cooldown_days": ent_cd,
      "sitout_after_sl_days": sit_cd,
    },
    "ledger": sim.get("ledger"),
    "skipped": sim.get("skipped"),
    "decision_summary": {
      "why_strategy": {
        "picked": strategy_id,
        "reason": chooser.get("reason"),
        "weights": chooser.get("weights"),
        "scores": chooser.get("scores"),
        "regime": regime,
        "lane": lane,
      },
      "why_tickers": [
        {
          "ticker": t.get("ticker"),
          "pick_order": t.get("pick_order"),
          "confidence": t.get("confidence"),
          "or_width_pct": t.get("or_width_pct"),
          "money_put": t.get("money_put"),
          "leverage": t.get("leverage"),
          "universe_rank": t.get("universe_rank"),
          "signal_reason": t.get("signal_reason"),
          "why_selected": t.get("why_selected"),
        }
        for t in trades
      ],
      "risk": {
        "max_positions": slots,
        "max_leverage": kwargs.get("max_leverage"),
        "max_daily_loss_pct": kwargs.get("max_daily_loss_pct"),
        "max_trade_risk_pct": kwargs.get("max_trade_risk_pct"),
        "conf_floor": kwargs.get("conf_floor"),
        "min_or_pct": kwargs.get("min_or_pct"),
      },
    },
    "disclaimer": (
      "Hybrid paper/sim — not investment advice. "
      + ("Research lane is not live-eligible. " if lane == "research" else "")
      + "North star: most profits under honest risk labels."
    ),
  }


def simulate_hybrid_window(
  *,
  window_id: str | None = None,
  start: str | None = None,
  end: str | None = None,
  capital: float = 10_000.0,
  market: str = "IN",
  lane: str = "product",
  force_strategy: str | None = None,
  record_learning: bool = True,
) -> dict[str, Any]:
  """Compound hybrid days across a window; compare to ceiling/floor."""
  from processor.benchmarks import window_specs

  if window_id:
    specs = {w["id"]: w for w in window_specs()}
    if window_id not in specs:
      return {"error": f"unknown window_id: {window_id}", "known": list(specs)}
    start = specs[window_id]["start"]
    end = specs[window_id]["end"]
  if not start or not end:
    return {"error": "need window_id or start+end"}

  days = _sessions(start, end)
  cap = float(capital)
  start_cap = cap
  daily: list[dict[str, Any]] = []
  trade_ids: list[str] = []
  min_ret = 999.0
  max_ret = -999.0
  peak = cap
  max_dd = 0.0
  last_chooser = None
  strategy_counts: dict[str, int] = {}

  for asof in days:
    # Rules ledger is read inside simulate_hybrid_day before any trade.
    day = simulate_hybrid_day(
      asof=asof,
      capital=cap,
      market=market,
      lane=lane,
      force_strategy=force_strategy,
      include_ticker_ranks=False,
      include_bars=False,
      record_learning=record_learning,
    )
    if day.get("error"):
      daily.append({"asof": asof, "error": day["error"]})
      continue
    ret = float(day.get("return_pct") or 0)
    cap = float(day.get("capital_end") or cap)
    peak = max(peak, cap)
    dd = 100.0 * (peak - cap) / peak if peak else 0.0
    max_dd = max(max_dd, dd)
    min_ret = min(min_ret, ret)
    max_ret = max(max_ret, ret)
    sid = str(day.get("strategy_id") or "")
    strategy_counts[sid] = strategy_counts.get(sid, 0) + 1
    last_chooser = day.get("chooser")
    for t in day.get("trades") or []:
      if t.get("trade_id"):
        trade_ids.append(str(t["trade_id"]))
    briefing = day.get("rules_briefing") or {}
    daily.append(
      {
        "asof": asof,
        "return_pct": ret,
        "capital_end": round(cap, 2),
        "strategy_id": sid,
        "n_trades": day.get("n_trades"),
        "chooser": day.get("chooser"),
        "sitout": bool(day.get("sitout")),
        "rules_summary": briefing.get("summary"),
        "rules_learn": day.get("rules_learn"),
      }
    )

  compound = round(100.0 * (cap - start_cap) / start_cap, 4) if start_cap else 0.0
  if min_ret > 100:
    min_ret = 0.0
  if max_ret < -100:
    max_ret = 0.0
  score = primary_score(compound_pct=compound, worst_day_pct=min_ret, max_dd_pct=max_dd)
  cmp = (
    compare_to_benchmarks(
      window_id=window_id or "custom",
      compound_pct=compound,
      worst_day_pct=min_ret,
      best_day_pct=max_ret,
      max_dd_pct=max_dd,
    )
    if window_id
    else {
      "run": {
        "compound_pct": compound,
        "worst_day_pct": min_ret,
        "best_day_pct": max_ret,
        "primary_score": score,
      }
    }
  )

  prev_wins = list_wins(limit=5)
  prev_best = None
  prev_eq = None
  for w in prev_wins:
    m = w.get("metrics") or {}
    if prev_best is None and m.get("primary_score") is not None:
      prev_best = float(m["primary_score"])
    if prev_eq is None and m.get("final_capital") is not None:
      prev_eq = float(m["final_capital"])

  wins = detect_wins_from_run(
    lane=lane,
    asof=None,
    window_id=window_id,
    compound_pct=compound,
    worst_day_pct=min_ret,
    best_day_pct=max_ret,
    primary_score=score,
    prev_best_primary=prev_best,
    prev_equity_high=prev_eq,
    final_capital=cap,
    start_capital=start_cap,
    beats_ceiling=bool(cmp.get("beats_ceiling")),
    gap_to_ceiling_pct=cmp.get("gap_to_ceiling_pct"),
    trade_ids=trade_ids,
  )

  return {
    "mode": "hybrid_window",
    "north_star": "most_profits",
    "window_id": window_id,
    "start": start,
    "end": end,
    "lane": lane,
    "n_days": len(days),
    "capital_start": start_cap,
    "capital_end": round(cap, 2),
    "compound_pct": compound,
    "worst_day_pct": round(min_ret, 4),
    "best_day_pct": round(max_ret, 4),
    "max_dd_pct": round(max_dd, 4),
    "primary_score": score,
    "strategy_counts": strategy_counts,
    "last_chooser": last_chooser,
    "benchmark": cmp,
    "wins": wins,
    "daily": daily,
    "disclaimer": (
      "Hybrid paper/sim window — not investment advice. "
      "Ceiling is aspiration/research; product lane uses risk caps."
    ),
  }
