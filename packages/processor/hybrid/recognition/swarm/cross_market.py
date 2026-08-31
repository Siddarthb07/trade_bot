"""Cross-market open cue agent (GIFT / SG-style overnight → NSE).

PIT-safe: only uses overnight proxy return known before the Indian cash open
(or before signal time). Does not use same-day NSE path.

Research note: legacy SGX Nifty migrated to GIFT Nifty (NSE IX) Jul 2023.
Direction of pre-open cue historically predicts open direction more reliably
than magnitude; India-specific events weaken the link.
"""

from __future__ import annotations

from typing import Any

from processor.hybrid.recognition.types import AgentMessage


def cross_market_open_message(
  *,
  overnight_gap_pct: float | None = None,
  asia_ret_pct: float | None = None,
  us_ret_pct: float | None = None,
  primary_side: str | None = None,
) -> AgentMessage:
  """Vote on whether overnight global/SG-style cues agree with the primary.

  overnight_gap_pct: (proxy_preopen - prev_nifty_close) / prev_nifty_close
  asia_ret_pct / us_ret_pct: optional overnight session returns (fractions).
  """
  if overnight_gap_pct is None and asia_ret_pct is None and us_ret_pct is None:
    return AgentMessage(
      agent="CrossMarketOpen",
      vote="annotate",
      status="cold_start",
      reason="no_overnight_cue",
      payload={},
    )

  gap = float(overnight_gap_pct) if overnight_gap_pct is not None else 0.0
  asia = float(asia_ret_pct) if asia_ret_pct is not None else 0.0
  us = float(us_ret_pct) if us_ret_pct is not None else 0.0
  # Composite: gap dominates; US/Asia as soft confirmation
  composite = gap + 0.35 * us + 0.25 * asia

  payload: dict[str, Any] = {
    "overnight_gap_pct": round(gap, 6) if overnight_gap_pct is not None else None,
    "asia_ret_pct": round(asia, 6) if asia_ret_pct is not None else None,
    "us_ret_pct": round(us, 6) if us_ret_pct is not None else None,
    "composite": round(composite, 6),
  }

  # Weak cue → annotate only (do not fake conviction)
  if abs(composite) < 0.0015:
    return AgentMessage(
      agent="CrossMarketOpen",
      vote="annotate",
      reason="cue_flat",
      payload=payload,
      status="ok",
    )

  cue_long = composite > 0
  if primary_side in ("buy", "sell"):
    agrees = (primary_side == "buy" and cue_long) or (primary_side == "sell" and not cue_long)
    # Large opposing gap → skip; agreeing gap → take; mild disagreement → annotate
    if agrees and abs(composite) >= 0.0025:
      return AgentMessage(
        agent="CrossMarketOpen",
        vote="take",
        reason="cue_agrees_primary",
        payload=payload,
        status="ok",
      )
    if (not agrees) and abs(composite) >= 0.004:
      return AgentMessage(
        agent="CrossMarketOpen",
        vote="skip",
        reason="cue_opposes_primary",
        payload=payload,
        status="ok",
      )
    return AgentMessage(
      agent="CrossMarketOpen",
      vote="annotate",
      reason="cue_weak_vs_primary",
      payload=payload,
      status="ok",
    )

  # No primary: cue alone only annotates (never sole fire authority)
  return AgentMessage(
    agent="CrossMarketOpen",
    vote="annotate",
    reason="cue_only_no_primary",
    payload=payload,
    status="ok",
  )


def cross_section_similarity_message(
  *,
  candidate_ret_1: float | None,
  peer_rets: list[float] | None = None,
  primary_side: str | None = None,
) -> AgentMessage:
  """Rank-style similarity: is candidate an outlier vs peers (dispersion)?

  High dispersion + candidate in top/bottom quartile → take if aligned with side.
  Low dispersion (everyone moving together) → skip crowded tape.
  """
  if candidate_ret_1 is None or not peer_rets or len(peer_rets) < 5:
    return AgentMessage(
      agent="CrossSectionSimilarity",
      vote="annotate",
      status="insufficient_data",
      reason="need_peers",
      payload={},
    )

  peers = sorted(float(x) for x in peer_rets)
  n = len(peers)
  med = peers[n // 2]
  p75 = peers[int(0.75 * (n - 1))]
  p25 = peers[int(0.25 * (n - 1))]
  iqr = p75 - p25
  cand = float(candidate_ret_1)
  payload = {
    "candidate_ret_1": round(cand, 6),
    "median": round(med, 6),
    "iqr": round(iqr, 6),
    "p75": round(p75, 6),
    "p25": round(p25, 6),
  }

  if iqr < 0.004:
    return AgentMessage(
      agent="CrossSectionSimilarity",
      vote="skip",
      reason="low_dispersion_crowded",
      payload=payload,
      status="ok",
    )

  top = cand >= p75
  bot = cand <= p25
  if primary_side == "buy" and top:
    return AgentMessage(
      agent="CrossSectionSimilarity",
      vote="take",
      reason="candidate_top_quartile",
      payload=payload,
      status="ok",
    )
  if primary_side == "sell" and bot:
    return AgentMessage(
      agent="CrossSectionSimilarity",
      vote="take",
      reason="candidate_bottom_quartile",
      payload=payload,
      status="ok",
    )
  if primary_side == "buy" and bot:
    return AgentMessage(
      agent="CrossSectionSimilarity",
      vote="skip",
      reason="long_but_laggard",
      payload=payload,
      status="ok",
    )
  return AgentMessage(
    agent="CrossSectionSimilarity",
    vote="annotate",
    reason="mid_pack",
    payload=payload,
    status="ok",
  )
