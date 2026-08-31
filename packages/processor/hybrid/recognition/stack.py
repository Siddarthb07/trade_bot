"""recognize_session — causal NSE recognition snapshot for Godfather swarm."""

from __future__ import annotations

from typing import Any, Sequence

from processor.hybrid.recognition.allocator import fractional_kelly, vol_target_mult
from processor.hybrid.recognition.detectors.changepoint import cusum_break_prob
from processor.hybrid.recognition.detectors.hmm import filtered_regime
from processor.hybrid.recognition.detectors.hurst import hurst_rs
from processor.hybrid.recognition.detectors.jumps import jump_day_flag
from processor.hybrid.recognition.geometry import build_geometry
from processor.hybrid.recognition.learn import (
  agent_accuracy_map,
  agent_weight,
  load_state,
)
from processor.hybrid.recognition.models.meta_label import score_take
from processor.hybrid.recognition.stubs import hawkes_message, kyle_message, vpin_message
from processor.hybrid.recognition.rules_ledger import rules_clerk_message
from processor.hybrid.recognition.swarm.cross_market import (
  cross_market_open_message,
  cross_section_similarity_message,
)
from processor.hybrid.recognition.swarm.line_geometry import line_geometry_message
from processor.hybrid.recognition.swarm.similarity import (
  DEFAULT_HIT_RATES,
  DEFAULT_TEMPLATES,
  similarity_message,
)
from processor.hybrid.recognition.swarm.specialists import (
  breadth_message,
  changepoint_message,
  decay_message,
  ghlz_message,
  hurst_message,
  jump_risk_message,
  momentum_message,
  orb_quality_message,
  outcome_learner_message,
  session_clock_message,
  vol_regime_message,
)
from processor.hybrid.recognition.swarm.supervisor import decide_agreement, pick_expert
from processor.hybrid.recognition.types import (
  AgentMessage,
  Allocation,
  Ecology,
  RecognitionSnapshot,
  RegimePosterior,
)


def _path_closes(bars: Sequence[dict[str, Any]]) -> list[float]:
  return [float(b.get("close") or 0) for b in bars]


def _with_weight(msg: AgentMessage, state: dict[str, Any]) -> AgentMessage:
  w = agent_weight(state, msg.agent)
  if abs(w - msg.weight) < 1e-9:
    return msg
  return AgentMessage(
    agent=msg.agent,
    vote=msg.vote,
    weight=w,
    reason=msg.reason,
    payload=msg.payload,
    status=msg.status,
  )


def recognize_session(
  *,
  asof: str,
  bars: Sequence[dict[str, Any]],
  daily_closes: Sequence[float] | None = None,
  primary_side: str | None = None,
  prev_close: float | None = None,
  universe_ret: float | None = None,
  btc_overnight_pct: float | None = None,
  overnight_gap_pct: float | None = None,
  asia_ret_pct: float | None = None,
  us_ret_pct: float | None = None,
  peer_rets: list[float] | None = None,
  candidate_ret_1: float | None = None,
  ecology: Ecology = "nse",
  tau: float | None = None,
  preferred_expert: str = "orwidth_orb",
  templates: dict[str, Sequence[float]] | None = None,
  hit_rates: dict[str, float] | None = None,
  learn_state: dict[str, Any] | None = None,
  candidate_ticker: str | None = None,
) -> RecognitionSnapshot:
  """Build a frozen recognition snapshot. Pure / causal on provided bars."""
  state = learn_state if learn_state is not None else load_state()
  eff_tau = float(tau if tau is not None else state.get("tau") or 0.55)
  meta_bias = float(state.get("meta_bias") or 0.0)
  hrs = hit_rates or state.get("hit_rates") or DEFAULT_HIT_RATES

  if ecology != "nse":
    msgs = (
      AgentMessage(agent="Supervisor", vote="skip", reason=f"ecology_{ecology}_not_product"),
      hawkes_message(ecology=ecology),
    )
    return RecognitionSnapshot(
      ecology=ecology,
      asof=asof,
      messages=msgs,
      agreement=decide_agreement(list(msgs), tau=eff_tau, primary_side=None),
      allocation=Allocation(size_mult=0.0, expert="cash", notes=("non_nse",)),
      primary_side=None,
    )

  geometry = build_geometry(
    bars,
    prev_close=prev_close,
    universe_ret=universe_ret,
    btc_overnight_pct=btc_overnight_pct,
  )

  closes_daily = list(daily_closes) if daily_closes is not None else _path_closes(bars)
  regime = filtered_regime(closes_daily)
  h = hurst_rs(closes_daily)
  brk, age = cusum_break_prob(closes_daily)
  jump = jump_day_flag(closes_daily)
  regime = RegimePosterior(
    p_trend=regime.p_trend,
    p_chop=regime.p_chop,
    p_risk_off=regime.p_risk_off,
    label=regime.label,
    hurst=None if h is None else round(h, 4),
    jump_day=jump,
    break_prob=brk,
    regime_age=age,
    status=regime.status,
  )

  path = _path_closes(bars)
  sim = similarity_message(
    path,
    templates or DEFAULT_TEMPLATES,
    hit_rates=hrs,
  )
  lines = line_geometry_message(list(bars))

  analog_hr = None
  if sim.payload.get("hit_rate") is not None:
    analog_hr = float(sim.payload["hit_rate"])
  p_take, meta_msg = score_take(
    primary_side=primary_side,
    geometry=geometry,
    regime=regime,
    analog_hit_rate=analog_hr,
    meta_bias=meta_bias,
  )

  orw = geometry.or_width_pct or 0.0
  if orw < 0.003:
    cost_vote = AgentMessage(agent="Cost", vote="skip", reason="or_lt_friction", payload={"or_width_pct": orw})
  else:
    cost_vote = AgentMessage(agent="Cost", vote="take", reason="or_gt_friction", payload={"or_width_pct": orw})

  cold = int(state.get("n_outcome_updates") or 0) < 3
  decay = decay_message(cold=cold, recent_skip_rate=float(state.get("recent_skip_rate") or 0.5))

  # Mandatory: read rules ledger BEFORE stacking votes (same mistakes banned)
  clerk_msg, briefing = rules_clerk_message(
    state,
    asof=asof,
    regime_label=regime.label,
    candidate_ticker=candidate_ticker,
  )

  regime_msg = AgentMessage(
    agent="Regime",
    vote="skip" if regime.label in ("risk_off", "chop") else "take",
    reason=f"label={regime.label}",
    payload={"posterior": {"trend": regime.p_trend, "chop": regime.p_chop, "risk_off": regime.p_risk_off}},
    status=regime.status,
  )
  geom_msg = AgentMessage(
    agent="Geometry",
    vote="annotate",
    reason=geometry.status,
    payload={"or_width_pct": geometry.or_width_pct, "ghlz_r1": geometry.ghlz_r1},
    status=geometry.status,
  )

  messages = [
    clerk_msg,
    geom_msg,
    regime_msg,
    sim,
    lines,
    meta_msg,
    cost_vote,
    decay,
    changepoint_message(break_prob=float(regime.break_prob or 0), regime_age=int(regime.regime_age or 0)),
    hurst_message(hurst=regime.hurst),
    jump_risk_message(jump_day=bool(regime.jump_day)),
    ghlz_message(list(bars), geometry=geometry),
    orb_quality_message(geometry=geometry, primary_side=primary_side),
    momentum_message(list(bars)),
    session_clock_message(list(bars)),
    breadth_message(universe_ret=universe_ret),
    vol_regime_message(geometry=geometry, regime=regime),
    cross_market_open_message(
      overnight_gap_pct=overnight_gap_pct,
      asia_ret_pct=asia_ret_pct,
      us_ret_pct=us_ret_pct,
      primary_side=primary_side,
    ),
    cross_section_similarity_message(
      candidate_ret_1=candidate_ret_1,
      peer_rets=peer_rets,
      primary_side=primary_side,
    ),
    outcome_learner_message(
      agent_accuracy=agent_accuracy_map(state),
      fleet_bias=float(state.get("fleet_bias") or 0.0),
    ),
    vpin_message(list(bars)),
    hawkes_message(ecology="nse", bars=list(bars)),
    kyle_message(list(bars)),
  ]
  messages = [_with_weight(m, state) for m in messages]

  weights = {m.agent: m.weight for m in messages}
  agreement = decide_agreement(messages, tau=eff_tau, primary_side=primary_side, weights=weights)
  alloc = pick_expert(tradeable=agreement.tradeable, ecology="nse", preferred=preferred_expert)

  vscale = vol_target_mult(realized_vol=geometry.rv_1d)
  k = fractional_kelly(p_take=p_take)
  size = 0.0 if not agreement.tradeable else min(1.0, vscale, max(k, 0.15))
  # Soft ledger: raise_tau / size_down from soft rules
  for r in briefing.get("soft_rules") or []:
    if r.get("action") == "raise_tau" and agreement.tradeable:
      pass  # τ already learned online; soft rules are tape-visible
  alloc = Allocation(
    size_mult=round(size, 4),
    expert=alloc.expert,
    kelly_frac=round(k, 4),
    vol_scale=round(vscale, 4),
    notes=alloc.notes + ("vol_kelly", "learn_loop", "rules_ledger"),
  )

  snap = RecognitionSnapshot(
    ecology="nse",
    asof=asof,
    geometry=geometry,
    regime=regime,
    messages=tuple(messages),
    agreement=agreement,
    allocation=alloc,
    primary_side=primary_side,
    meta_p_take=round(p_take, 4),
    project="godfather",
  )
  # Attach briefing for desk / engine (via to_dict extension)
  d = snap.to_dict()
  d["daily_briefing"] = briefing
  # Return typed snapshot; engine reads messages; briefing also on learn state file
  return snap
