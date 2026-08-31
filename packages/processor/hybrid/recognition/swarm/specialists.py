"""Extra deterministic specialists — no LLM on the fire path."""

from __future__ import annotations

from typing import Any, Sequence

from processor.hybrid.recognition.detectors.ghlz import early_session_return
from processor.hybrid.recognition.types import AgentMessage, RegimePosterior, SessionGeometry


def changepoint_message(*, break_prob: float, regime_age: int) -> AgentMessage:
  # Fresh CUSUM break into trend is take; stale / noisy break → skip
  if break_prob >= 0.65 and regime_age <= 8:
    vote = "take"
    reason = "fresh_break"
  elif break_prob >= 0.55 and regime_age > 20:
    vote = "skip"
    reason = "stale_break"
  elif break_prob < 0.35:
    vote = "annotate"
    reason = "no_break"
  else:
    vote = "annotate"
    reason = "break_uncertain"
  return AgentMessage(
    agent="Changepoint",
    vote=vote,  # type: ignore[arg-type]
    reason=reason,
    payload={"break_prob": round(break_prob, 4), "regime_age": regime_age},
    status="ok",
  )


def hurst_message(*, hurst: float | None) -> AgentMessage:
  if hurst is None:
    return AgentMessage(agent="Hurst", vote="annotate", status="insufficient_data", reason="short_series")
  if hurst >= 0.55:
    vote, reason = "take", "persistent_trend"
  elif hurst <= 0.45:
    vote, reason = "skip", "mean_reverting"
  else:
    vote, reason = "annotate", "random_walkish"
  return AgentMessage(
    agent="Hurst",
    vote=vote,  # type: ignore[arg-type]
    reason=reason,
    payload={"hurst": round(hurst, 4)},
    status="ok",
  )


def jump_risk_message(*, jump_day: bool) -> AgentMessage:
  if jump_day:
    return AgentMessage(
      agent="JumpRisk",
      vote="skip",
      reason="jump_day_flag",
      payload={"jump_day": True},
      status="ok",
    )
  return AgentMessage(
    agent="JumpRisk",
    vote="take",
    reason="no_jump",
    payload={"jump_day": False},
    status="ok",
  )


def ghlz_message(bars: Sequence[dict[str, Any]], *, geometry: SessionGeometry) -> AgentMessage:
  r1 = geometry.ghlz_r1
  if r1 is None:
    r1 = early_session_return(bars, n=6)
  if r1 is None:
    return AgentMessage(agent="GHLZ", vote="annotate", status="insufficient_data", reason="no_early_bars")
  if r1 >= 0.004:
    vote, reason = "take", "early_bid_strength"
  elif r1 <= -0.004:
    vote, reason = "skip", "early_offer_pressure"
  else:
    vote, reason = "annotate", "flat_open"
  return AgentMessage(
    agent="GHLZ",
    vote=vote,  # type: ignore[arg-type]
    reason=reason,
    payload={"ghlz_r1": round(float(r1), 5)},
    status="ok",
  )


def orb_quality_message(*, geometry: SessionGeometry, primary_side: str | None) -> AgentMessage:
  if primary_side not in ("buy", "sell"):
    return AgentMessage(agent="ORBQuality", vote="skip", reason="no_primary", status="ok")
  orw = geometry.or_width_pct
  if orw is None:
    return AgentMessage(agent="ORBQuality", vote="annotate", status="insufficient_data", reason="no_or")
  # Sweet spot: wide enough to pay friction, not so wild that ORB is noise
  if 0.0035 <= orw <= 0.018:
    vote, reason = "take", "or_sweet_spot"
  elif orw < 0.0025:
    vote, reason = "skip", "or_too_tight"
  elif orw > 0.028:
    vote, reason = "skip", "or_chaotic"
  else:
    vote, reason = "annotate", "or_borderline"
  return AgentMessage(
    agent="ORBQuality",
    vote=vote,  # type: ignore[arg-type]
    reason=reason,
    payload={"or_width_pct": round(orw, 6)},
    status="ok",
  )


def momentum_message(bars: Sequence[dict[str, Any]]) -> AgentMessage:
  if len(bars) < 8:
    return AgentMessage(agent="Momentum", vote="annotate", status="insufficient_data", reason="short_path")
  closes = [float(b.get("close") or 0) for b in bars]
  if closes[0] <= 0 or closes[-1] <= 0:
    return AgentMessage(agent="Momentum", vote="annotate", status="insufficient_data", reason="bad_px")
  ret = closes[-1] / closes[max(0, len(closes) - 6)] - 1.0
  if ret >= 0.004:
    vote, reason = "take", "short_momentum_up"
  elif ret <= -0.004:
    vote, reason = "skip", "short_momentum_down"
  else:
    vote, reason = "annotate", "flat_momentum"
  return AgentMessage(
    agent="Momentum",
    vote=vote,  # type: ignore[arg-type]
    reason=reason,
    payload={"ret_5": round(ret, 5)},
    status="ok",
  )


def session_clock_message(bars: Sequence[dict[str, Any]]) -> AgentMessage:
  """Prefer mid-session continuation; skip late-day ORB chases."""
  n = len(bars)
  if n < 6:
    return AgentMessage(agent="SessionClock", vote="annotate", status="insufficient_data", reason="short")
  # 5m NSE ~75 bars/day; early <15, late >55
  if n <= 18:
    vote, reason = "annotate", "early_session"
  elif n <= 50:
    vote, reason = "take", "prime_window"
  else:
    vote, reason = "skip", "late_session"
  return AgentMessage(
    agent="SessionClock",
    vote=vote,  # type: ignore[arg-type]
    reason=reason,
    payload={"n_bars": n},
    status="ok",
  )


def breadth_message(*, universe_ret: float | None) -> AgentMessage:
  if universe_ret is None:
    return AgentMessage(agent="Breadth", vote="annotate", status="cold_start", reason="no_universe_ret")
  if universe_ret >= 0.002:
    vote, reason = "take", "tape_bid"
  elif universe_ret <= -0.002:
    vote, reason = "skip", "tape_offer"
  else:
    vote, reason = "annotate", "tape_flat"
  return AgentMessage(
    agent="Breadth",
    vote=vote,  # type: ignore[arg-type]
    reason=reason,
    payload={"universe_ret": round(universe_ret, 5)},
    status="ok",
  )


def vol_regime_message(*, geometry: SessionGeometry, regime: RegimePosterior) -> AgentMessage:
  rv = geometry.rv_1d
  if rv is None:
    return AgentMessage(agent="VolRegime", vote="annotate", status="insufficient_data", reason="no_rv")
  if regime.label == "risk_off" or (rv is not None and rv > 0.025):
    return AgentMessage(
      agent="VolRegime",
      vote="skip",
      reason="elevated_vol",
      payload={"rv_1d": round(rv, 5), "label": regime.label},
      status="ok",
    )
  if rv < 0.004:
    return AgentMessage(
      agent="VolRegime",
      vote="skip",
      reason="dead_tape",
      payload={"rv_1d": round(rv, 5)},
      status="ok",
    )
  return AgentMessage(
    agent="VolRegime",
    vote="take",
    reason="tradable_vol",
    payload={"rv_1d": round(rv, 5)},
    status="ok",
  )


def outcome_learner_message(
  *,
  agent_accuracy: dict[str, float],
  fleet_bias: float,
) -> AgentMessage:
  """Fleet-level learned prior from recent outcomes (not a hard veto)."""
  # Soft lean: fleet_bias > 0 → recent takes worked
  if fleet_bias >= 0.08:
    vote, reason = "take", "learned_edge_positive"
  elif fleet_bias <= -0.08:
    vote, reason = "skip", "learned_edge_negative"
  else:
    vote, reason = "annotate", "learned_edge_flat"
  return AgentMessage(
    agent="OutcomeLearner",
    vote=vote,  # type: ignore[arg-type]
    reason=reason,
    payload={"fleet_bias": round(fleet_bias, 4), "n_tracked": len(agent_accuracy)},
    weight=1.25,
    status="ok",
  )


def decay_message(*, cold: bool, recent_skip_rate: float) -> AgentMessage:
  if cold:
    return AgentMessage(agent="Decay", vote="annotate", reason="ledger_warming", status="cold_start")
  if recent_skip_rate >= 0.75:
    return AgentMessage(
      agent="Decay",
      vote="skip",
      reason="high_recent_skip_cluster",
      payload={"recent_skip_rate": round(recent_skip_rate, 3)},
      status="ok",
    )
  if recent_skip_rate <= 0.25:
    return AgentMessage(
      agent="Decay",
      vote="take",
      reason="recent_fire_ok",
      payload={"recent_skip_rate": round(recent_skip_rate, 3)},
      status="ok",
    )
  return AgentMessage(
    agent="Decay",
    vote="annotate",
    reason="decay_neutral",
    payload={"recent_skip_rate": round(recent_skip_rate, 3)},
    status="ok",
  )
