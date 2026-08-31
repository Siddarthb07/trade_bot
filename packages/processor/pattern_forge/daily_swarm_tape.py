"""Build a readable agent tape for daily_swing decisions (Pattern Lab inspector).

When hard_veto=True, skip votes from Regime / CrossMarket / Similarity / Breadth
make agreement.tradeable=False so the runner must sit cash (never amplify).
"""

from __future__ import annotations

from typing import Any

from processor.hybrid.recognition.swarm.cross_market import (
  cross_market_open_message,
  cross_section_similarity_message,
)
from processor.pattern_forge.market_regime_proxy import soft_regime

HARD_VETO_AGENTS = frozenset({"Regime", "CrossMarketOpen", "CrossSectionSimilarity", "BreadthRegime"})


def _msg(agent: str, vote: str, reason: str, *, weight: float = 1.0, status: str = "ok", payload: dict | None = None) -> dict[str, Any]:
  return {
    "agent": agent,
    "vote": vote,
    "reason": reason,
    "weight": weight,
    "status": status,
    "payload": payload or {},
  }


def daily_swarm_tape(
  choice: dict[str, Any],
  *,
  market_closes: list[float] | None = None,
  peer_rets: list[float] | None = None,
  candidate_ret_1: float | None = None,
  overnight_gap_pct: float | None = None,
  asia_ret_pct: float | None = None,
  us_ret_pct: float | None = None,
  hard_veto: bool = False,
  profit_guard_note: str | None = None,
  feed_status: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  """Return (messages, agreement) for ledger + dash."""
  regime = soft_regime(list(market_closes or []))
  primary = choice.get("primary") or {}
  side = str(primary.get("side") or "flat")
  picked = str(choice.get("picked") or "cash")
  breadth = choice.get("breadth") or {}
  msgs: list[dict[str, Any]] = []

  msgs.append(
    _msg(
      "Regime",
      "skip" if regime == "risk_off" else ("take" if regime == "trend" else "annotate"),
      f"label={regime}",
      payload={"regime": regime},
    )
  )

  # BreadthRegime — veto-only when stressed
  frac = breadth.get("frac_above_ma20")
  stress = bool(breadth.get("stress"))
  if frac is None:
    msgs.append(_msg("BreadthRegime", "annotate", "no_breadth", status="cold_start"))
  elif stress:
    msgs.append(
      _msg(
        "BreadthRegime",
        "skip",
        f"breadth_stress:{frac}",
        payload={"frac_above_ma20": frac, "n": breadth.get("n")},
      )
    )
  else:
    msgs.append(
      _msg(
        "BreadthRegime",
        "annotate" if float(frac) < 0.45 else "take",
        f"frac_above_ma20={frac}",
        payload={"frac_above_ma20": frac, "n": breadth.get("n")},
      )
    )

  if picked == "cash":
    msgs.append(_msg("DailySwingChooser", "skip", str(choice.get("reason") or "cash"), payload={"ranked_top": (choice.get("ranked_top") or [])[:5]}))
  else:
    msgs.append(
      _msg(
        "DailySwingChooser",
        "take",
        str(primary.get("reason") or choice.get("reason") or "picked"),
        payload={"ticker": picked, "score": primary.get("score"), "confidence": primary.get("confidence"), "side": side},
      )
    )

  for i, row in enumerate((choice.get("ranked_top") or [])[:5]):
    msgs.append(
      _msg(
        f"PeerRank#{i+1}",
        "annotate" if row.get("ticker") != picked else "take",
        f"{row.get('ticker')} score={row.get('score')} side={row.get('side')}",
        payload={"ticker": row.get("ticker"), "score": row.get("score"), "reason": row.get("reason")},
        weight=0.5,
      )
    )

  cm = cross_market_open_message(
    overnight_gap_pct=overnight_gap_pct,
    asia_ret_pct=asia_ret_pct,
    us_ret_pct=us_ret_pct,
    primary_side=side if side in ("buy", "sell") else None,
  )
  cm_payload = dict(cm.payload or {})
  if feed_status:
    cm_payload["feed_status"] = feed_status
  msgs.append(_msg(cm.agent, cm.vote, cm.reason, weight=cm.weight, status=cm.status, payload=cm_payload))

  cs = cross_section_similarity_message(
    candidate_ret_1=candidate_ret_1,
    peer_rets=peer_rets,
    primary_side=side if side in ("buy", "sell") else None,
  )
  msgs.append(_msg(cs.agent, cs.vote, cs.reason, weight=cs.weight, status=cs.status, payload=dict(cs.payload or {})))

  msgs.append(_msg("Cost", "take" if picked != "cash" else "annotate", "fo_cost_model_12bps", payload={"model": "IN_FO"}))
  msgs.append(_msg("NoRuin", "annotate", "checked_pre_trade", status="ok"))

  if profit_guard_note:
    msgs.append(
      _msg(
        "ProfitGuard",
        "annotate",
        profit_guard_note,
        payload={"note": profit_guard_note, "size_mult": choice.get("size_mult")},
      )
    )
  else:
    msgs.append(_msg("ProfitGuard", "annotate", "idle", status="ok"))

  hard_skips = [m for m in msgs if m["agent"] in HARD_VETO_AGENTS and m["vote"] == "skip"]
  take_n = sum(1 for m in msgs if m["vote"] == "take")
  skip_n = sum(1 for m in msgs if m["vote"] == "skip")

  if hard_veto:
    tradeable = picked != "cash" and regime != "risk_off" and not hard_skips
    reason = "ok" if tradeable else (hard_skips[0]["reason"] if hard_skips else (choice.get("reason") or "swarm_hard_veto"))
  else:
    tradeable = picked != "cash" and regime != "risk_off" and skip_n < take_n + 2
    reason = "ok" if tradeable and picked != "cash" else (choice.get("reason") or "swarm_block")

  agreement = {
    "score": round(take_n / max(1, take_n + skip_n), 4),
    "tradeable": bool(tradeable and picked != "cash"),
    "collapsed_votes": skip_n,
    "raw_skip_votes": skip_n,
    "hard_veto": hard_veto,
    "hard_skip_agents": [m["agent"] for m in hard_skips],
    "tau": 0.5,
    "reason": reason,
  }
  return msgs, agreement
