"""Pattern Forge session — synthetic-friendly, clean-PIT helpers.

Combines primary signal + recognition swarm + no-ruin + F&O short gate.
No network I/O: caller supplies bars / daily / library.
"""

from __future__ import annotations

from typing import Any, Sequence

from processor.costs import IN_COST
from processor.fo_universe import allow_short
from processor.hybrid.recognition import recognize_session
from processor.no_ruin import NoRuinConfig, apply_no_ruin_to_leverage, risk_budget, state_dict
from processor.pattern_forge.analogs import analog_signal
from processor.pattern_forge.candles import candle_signal
from processor.session_guard import apply_session_guards, daily_loss_halted
from processor.strategies import session_or_breakout
from processor.two_sided import normalize_side, notional_pnl, path_exit_two_sided


def _log_session_outcome(
  *,
  out: dict[str, Any],
  run_id: str | None,
  iteration_id: str | None,
) -> None:
  try:
    from processor.pattern_forge.ledger import log_decision, log_trade

    rec = out.get("recognition") or {}
    agreement = rec.get("agreement") or {}
    messages = rec.get("messages") or []
    choice = "fire" if out.get("trades") else "skip"
    if out.get("skip_reason") == "no_ruin_halt":
      choice = "no_ruin"
    log_decision(
      {
        "asof": out.get("asof"),
        "ticker": out.get("ticker"),
        "family": out.get("family"),
        "run_id": run_id,
        "iteration_id": iteration_id,
        "choice": choice,
        "primary": out.get("primary"),
        "hybrid_choice": out.get("hybrid_choice"),
        "swarm_agreement": agreement,
        "swarm_messages": [
          {
            "agent": m.get("agent"),
            "vote": m.get("vote"),
            "reason": m.get("reason"),
            "weight": m.get("weight"),
            "status": m.get("status"),
            "payload": m.get("payload") if isinstance(m.get("payload"), dict) else {},
          }
          for m in messages
          if isinstance(m, dict)
        ][:48],
        "no_ruin": out.get("no_ruin"),
        "skip_reason": out.get("skip_reason"),
        "notes": out.get("notes") or [],
      }
    )
    for t in out.get("trades") or []:
      log_trade(
        {
          **t,
          "asof": out.get("asof"),
          "run_id": run_id,
          "iteration_id": iteration_id,
          "family": out.get("family"),
        }
      )
  except Exception:
    pass


def _closes(bars: Sequence[dict[str, Any]]) -> list[float]:
  return [float(b.get("close") or 0) for b in bars]


def primary_signal(
  family: str,
  *,
  session_bars: Sequence[dict[str, Any]],
  daily_bars_before: Sequence[dict[str, Any]] | None = None,
  analog_library: Sequence[dict[str, Any]] | None = None,
  daily_closes: Sequence[float] | None = None,
  long_only: bool = False,
  hybrid_min_score: float = 0.15,
) -> dict[str, Any]:
  fam = family.lower().strip()
  if fam in ("hybrid_stock_market", "hybrid", "stock_market_hybrid"):
    from processor.pattern_forge.hybrid_chooser import choose_family_for_stock

    choice = choose_family_for_stock(
      session_bars,
      daily_closes=daily_closes,
      daily_bars_before=daily_bars_before,
      analog_library=analog_library,
      long_only=long_only,
      min_score=hybrid_min_score,
    )
    primary = dict(choice.get("primary") or {})
    primary["hybrid_choice"] = {
      "picked": choice.get("picked"),
      "scores": choice.get("scores"),
      "regime": choice.get("regime"),
      "reason": choice.get("reason"),
    }
    if choice.get("picked") == "cash":
      primary["side"] = "flat"
      primary["reason"] = choice.get("reason") or "hybrid_cash"
    return primary
  if fam in ("pattern_candle", "candle"):
    return candle_signal(daily_bars_before or [], session_bars=session_bars)
  if fam in ("pattern_analog", "analog"):
    return analog_signal(_closes(session_bars), analog_library or [])
  if fam in ("orb_two_sided", "orb2s", "orwidth_orb"):
    sob = session_or_breakout(list(session_bars))
    side = str(sob.get("side") or "flat")
    score = float(sob.get("score") or 0)
    if side == "sell" and score <= 0:
      score = float(sob.get("or_width_pct") or 0) * 10.0
    conf = min(0.85, 0.55 + score * 0.5) if side in ("buy", "sell") else 0.5
    return {
      "side": side,
      "confidence": conf,
      "reason": str(sob.get("reason") or "orb"),
      "or_width_pct": sob.get("or_width_pct"),
      "entry_i": sob.get("entry_i"),
      "entry_px": sob.get("entry_px"),
    }
  return {"side": "flat", "confidence": 0.5, "reason": f"unknown_family:{family}"}


def simulate_pattern_session(
  *,
  asof: str,
  ticker: str,
  session_bars: Sequence[dict[str, Any]],
  capital: float = 10_000.0,
  starting_capital: float | None = None,
  peak_equity: float | None = None,
  family: str = "pattern_candle",
  daily_bars_before: Sequence[dict[str, Any]] | None = None,
  analog_library: Sequence[dict[str, Any]] | None = None,
  daily_closes: Sequence[float] | None = None,
  sleeve_frac: float | None = None,
  no_ruin_cfg: NoRuinConfig | None = None,
  soft_trail_arm: float = 0.025,
  soft_trail: float = 0.01,
  sl: float = 0.01,
  preferred_expert: str | None = None,
  tau: float | None = None,
  run_id: str | None = None,
  iteration_id: str | None = None,
  log_ledger: bool = True,
  long_only: bool = False,
  min_confidence: float = 0.0,
  hybrid_min_score: float = 0.15,
) -> dict[str, Any]:
  """One ticker / one session. Returns trades + recognition + no-ruin state."""
  cfg = no_ruin_cfg or NoRuinConfig()
  start_book = float(starting_capital if starting_capital is not None else capital)
  peak = float(peak_equity if peak_equity is not None else max(start_book, capital))
  nr = risk_budget(
    equity=capital,
    starting_capital=start_book,
    peak_equity=peak,
    sleeve_frac=sleeve_frac,
    cfg=cfg,
  )

  def finish(base: dict[str, Any]) -> dict[str, Any]:
    if log_ledger:
      _log_session_outcome(out=base, run_id=run_id, iteration_id=iteration_id)
    return base

  base: dict[str, Any] = {
    "ok": True,
    "asof": asof,
    "ticker": ticker,
    "family": family,
    "capital_start": capital,
    "capital_end": capital,
    "trades": [],
    "no_ruin": state_dict(nr),
    "notes": [],
  }

  if nr.halted:
    base["notes"].append(f"no_ruin_halt:{nr.reason}")
    base["skip_reason"] = "no_ruin_halt"
    return finish(base)

  _ = daily_loss_halted(capital, capital, cfg.max_daily_loss_pct)

  primary = primary_signal(
    family,
    session_bars=session_bars,
    daily_bars_before=daily_bars_before,
    analog_library=analog_library,
    daily_closes=daily_closes,
    long_only=long_only,
    hybrid_min_score=hybrid_min_score,
  )
  side = normalize_side(str(primary.get("side")))
  base["primary"] = primary
  if primary.get("hybrid_choice"):
    base["hybrid_choice"] = primary["hybrid_choice"]

  if side is None:
    base["skip_reason"] = "flat_primary"
    base["notes"].append(primary.get("reason") or "flat")
    return finish(base)

  if long_only and side == "short":
    base["skip_reason"] = "long_only_block_short"
    base["notes"].append("long_only")
    return finish(base)

  if float(primary.get("confidence") or 0) < float(min_confidence or 0):
    base["skip_reason"] = "below_min_confidence"
    return finish(base)

  if side == "short":
    ok_s, why = allow_short(ticker)
    if not ok_s:
      base["skip_reason"] = why
      base["notes"].append(why)
      return finish(base)

  preferred = preferred_expert or family
  if family in ("hybrid_stock_market", "hybrid", "stock_market_hybrid"):
    hc = primary.get("hybrid_choice") or {}
    preferred = str(hc.get("picked") or "cash")
    if preferred == "cash":
      preferred = "pattern_candle"
  rec = recognize_session(
    asof=asof,
    bars=session_bars,
    daily_closes=list(daily_closes) if daily_closes is not None else _closes(session_bars),
    primary_side="buy" if side == "long" else "sell",
    preferred_expert=preferred,
    tau=tau,
    candidate_ticker=ticker,
  )
  base["recognition"] = rec.to_dict()
  if not rec.agreement.tradeable:
    base["skip_reason"] = f"swarm_skip:{rec.agreement.reason}"
    base["notes"].append(rec.agreement.reason)
    return finish(base)

  closes = _closes(session_bars)
  entry_i = int(primary.get("entry_i") or min(5, max(0, len(closes) - 2)))
  if entry_i >= len(closes) - 1:
    base["skip_reason"] = "no_path"
    return finish(base)

  size_mult = float(rec.allocation.size_mult or 0.0)
  if size_mult <= 0:
    base["skip_reason"] = "size_mult_zero"
    return finish(base)

  lev = min(cfg.max_leverage, max(1.0, float(primary.get("confidence") or 0.55) * 4.0))
  lev, gnotes = apply_session_guards(
    lev,
    sl_frac=sl,
    equity=capital,
    cash_start=capital,
    max_trade_risk_pct=cfg.max_trade_risk_pct,
    max_daily_loss_pct=cfg.max_daily_loss_pct,
  )
  lev, nnotes = apply_no_ruin_to_leverage(lev * size_mult, state=nr, cfg=cfg)
  if lev <= 0:
    base["skip_reason"] = "leverage_zero"
    base["notes"].extend(gnotes + nnotes)
    return finish(base)

  slot = nr.risk_budget
  notional = slot * lev
  entry_px = float(closes[entry_i])
  path = path_exit_two_sided(
    closes,
    entry_i,
    "buy" if side == "long" else "sell",
    sl=sl,
    soft_trail_arm=soft_trail_arm,
    soft_trail=soft_trail,
    protect_only=True,
  )
  if not path.get("ok"):
    base["skip_reason"] = path.get("reason") or "path_fail"
    return finish(base)

  fees = IN_COST.fee_on_notional(notional, sides=2)
  pnl = notional_pnl(notional, float(path["pnl_frac"]), fees)
  trade = {
    "ticker": ticker,
    "side": side,
    "entry_i": entry_i,
    "exit_i": path["exit_i"],
    "entry_price": round(entry_px, 4),
    "exit_price": round(float(path["exit_px"]), 4),
    "entry_notional": round(notional, 2),
    "fees": round(fees, 4),
    "pnl": pnl,
    "pnl_pct": round(100.0 * float(path["pnl_frac"]), 3),
    "exit_reason": path["exit_reason"],
    "leverage": round(lev, 4),
    "family": family,
    "signal_reason": primary.get("reason"),
    "guard_notes": gnotes + nnotes,
    "sleeve_frac": nr.sleeve_frac,
  }
  end = round(capital + pnl, 2)
  base["trades"] = [trade]
  base["capital_end"] = end
  base["notes"].extend(gnotes + nnotes)
  return finish(base)
