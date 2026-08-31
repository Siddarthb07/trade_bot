"""Meta-labeler — may only veto / size; never invent side (AFML Ch. 3)."""

from __future__ import annotations

from processor.hybrid.recognition.models.triple_barrier import first_barrier_touch, meta_label_from_barrier
from processor.hybrid.recognition.types import AgentMessage, RegimePosterior, SessionGeometry


def score_take(
  *,
  primary_side: str | None,
  geometry: SessionGeometry,
  regime: RegimePosterior,
  analog_hit_rate: float | None = None,
  meta_bias: float = 0.0,
) -> tuple[float, AgentMessage]:
  """Heuristic P(take) until a fitted classifier exists. Never flips side."""
  if primary_side not in ("buy", "sell"):
    return 0.0, AgentMessage(agent="MetaLabel", vote="skip", reason="no_primary_side", status="ok")

  p = 0.55 + float(meta_bias or 0.0)
  if regime.label == "risk_off":
    p -= 0.25
  elif regime.label == "chop":
    p -= 0.12
  elif regime.label == "trend":
    p += 0.08

  if geometry.or_width_pct is not None:
    if geometry.or_width_pct < 0.002:
      p -= 0.15
    elif geometry.or_width_pct > 0.01:
      p += 0.05

  if analog_hit_rate is not None:
    p = 0.6 * p + 0.4 * float(analog_hit_rate)

  p = float(min(0.95, max(0.05, p)))
  # Hard veto only on clearly bad takes; soft skip band lets agreement decide
  if p >= 0.48:
    vote = "take"
    hard = False
  elif p >= 0.40:
    vote = "skip"
    hard = False
  else:
    vote = "skip"
    hard = True
  return p, AgentMessage(
    agent="MetaLabel",
    vote=vote,  # type: ignore[arg-type]
    reason=f"p_take={p:.3f}",
    payload={"p_take": p, "primary_side": primary_side, "hard": hard, "meta_bias": meta_bias},
    status="ok",
  )


def label_path_for_training(
  path: list[float],
  *,
  entry: float,
  side: str,
  tp_pct: float = 0.01,
  sl_pct: float = 0.005,
  max_bars: int = 48,
) -> int:
  hit, _ = first_barrier_touch(path, entry=entry, side=side, tp_pct=tp_pct, sl_pct=sl_pct, max_bars=max_bars)
  return meta_label_from_barrier(hit)
