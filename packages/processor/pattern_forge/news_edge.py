"""NewsEdgeScan — swarm agent for off-market / tape-implied news edge.

Honest scope: this is NOT NLP headline scraping. It scores PIT-safe proxies that
usually move with macro news (US overnight, Asia, local gap) plus idiosyncratic
flow (candidate 1d vs peers). Votes never amplify size; skip → soft size in runner.
"""

from __future__ import annotations

from typing import Any

from processor.hybrid.recognition.types import AgentMessage


def news_edge_message(
  *,
  overnight_gap_pct: float | None = None,
  asia_ret_pct: float | None = None,
  us_ret_pct: float | None = None,
  candidate_ret_1: float | None = None,
  peer_rets: list[float] | None = None,
  primary_side: str | None = None,
  asof: str | None = None,
) -> AgentMessage:
  """Macro news tape + relative flow vote for the daily_swing swarm."""
  us = float(us_ret_pct) if us_ret_pct is not None else None
  asia = float(asia_ret_pct) if asia_ret_pct is not None else None
  gap = float(overnight_gap_pct) if overnight_gap_pct is not None else None

  if us is None and asia is None and gap is None and candidate_ret_1 is None:
    return AgentMessage(
      agent="NewsEdgeScan",
      vote="annotate",
      status="cold_start",
      reason="no_news_tape",
      payload={"asof": asof},
    )

  # Macro risk score: large US dump or dual US+Asia soft dump ≈ risk-off news
  macro_risk = 0.0
  tags: list[str] = []
  if us is not None:
    if us <= -0.012:
      macro_risk += 1.0
      tags.append("us_hard_risk_off")
    elif us <= -0.006:
      macro_risk += 0.55
      tags.append("us_soft_risk_off")
    elif us >= 0.01:
      macro_risk -= 0.45
      tags.append("us_risk_on")
  if asia is not None:
    if asia <= -0.01:
      macro_risk += 0.55
      tags.append("asia_risk_off")
    elif asia >= 0.008:
      macro_risk -= 0.25
      tags.append("asia_risk_on")
  if gap is not None and gap <= -0.008:
    macro_risk += 0.4
    tags.append("local_gap_down")

  # Idiosyncratic flow: candidate beats peer median → positive "stock news/flow"
  flow = None
  peers = [float(x) for x in (peer_rets or []) if x is not None]
  if candidate_ret_1 is not None and peers:
    med = sorted(peers)[len(peers) // 2]
    flow = float(candidate_ret_1) - float(med)
    if flow >= 0.01:
      tags.append("flow_leader")
    elif flow <= -0.01:
      tags.append("flow_laggard")

  payload: dict[str, Any] = {
    "asof": asof,
    "us_ret_pct": round(us, 6) if us is not None else None,
    "asia_ret_pct": round(asia, 6) if asia is not None else None,
    "overnight_gap_pct": round(gap, 6) if gap is not None else None,
    "macro_risk": round(macro_risk, 4),
    "flow_vs_peers": round(flow, 6) if flow is not None else None,
    "tags": tags,
    "claim": "tape_implied_news_proxy_not_nlp_headlines",
  }

  side = primary_side if primary_side in ("buy", "sell") else None

  # Hard risk-off news vs long → skip
  if side == "buy" and macro_risk >= 1.0:
    return AgentMessage(
      agent="NewsEdgeScan",
      vote="skip",
      reason=f"macro_news_risk:{','.join(tags) or 'elevated'}",
      payload=payload,
      status="ok",
    )

  # Soft risk-off without flow leadership → skip
  if side == "buy" and macro_risk >= 0.7 and (flow is None or flow < 0.005):
    return AgentMessage(
      agent="NewsEdgeScan",
      vote="skip",
      reason=f"soft_news_risk_no_flow:{','.join(tags)}",
      payload=payload,
      status="ok",
    )

  # Risk-on + flow leader → take (edge confirmation)
  if side == "buy" and macro_risk <= -0.3 and flow is not None and flow >= 0.008:
    return AgentMessage(
      agent="NewsEdgeScan",
      vote="take",
      reason="news_tape_confirms_flow",
      payload=payload,
      status="ok",
    )

  if side == "buy" and flow is not None and flow >= 0.012 and macro_risk < 0.55:
    return AgentMessage(
      agent="NewsEdgeScan",
      vote="take",
      reason="idiosyncratic_flow_edge",
      payload=payload,
      status="ok",
    )

  return AgentMessage(
    agent="NewsEdgeScan",
    vote="annotate",
    reason="news_tape_neutral",
    payload=payload,
    status="ok",
  )


def news_edge_size_mult(vote: str, *, soft_mult: float = 0.4) -> float:
  """Map NewsEdge vote → size multiplier (never amplify)."""
  if vote == "skip":
    return max(0.0, min(1.0, float(soft_mult)))
  return 1.0
