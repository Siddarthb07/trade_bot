"""Supervisor — weighted agreement; collapse correlated skips; never invent side."""

from __future__ import annotations

from processor.hybrid.recognition.ecology import assert_no_cross_softmax
from processor.hybrid.recognition.types import AgentMessage, Agreement, Allocation


_CORRELATED = frozenset(
  {
    "Similarity",
    "LineGeometry",
    "Regime",
    "Hurst",
    "Changepoint",
    "Momentum",
    "GHLZ",
  }
)


def collapse_skips(messages: list[AgentMessage]) -> tuple[int, int]:
  """Return (raw_skip_count, collapsed_skip_groups)."""
  skips = [m for m in messages if m.vote == "skip"]
  raw = len(skips)
  correlated = [m for m in skips if m.agent in _CORRELATED]
  others = [m for m in skips if m.agent not in _CORRELATED]
  collapsed = (1 if correlated else 0) + len(others)
  return raw, collapsed


def decide_agreement(
  messages: list[AgentMessage],
  *,
  tau: float = 0.6,
  primary_side: str | None,
  weights: dict[str, float] | None = None,
) -> Agreement:
  if primary_side not in ("buy", "sell"):
    return Agreement(score=0.0, tradeable=False, tau=tau, reason="no_primary")

  voters = [m for m in messages if m.vote in ("take", "skip") and m.status == "ok"]
  if not voters:
    return Agreement(score=0.0, tradeable=False, tau=tau, reason="no_voters")

  wmap = weights or {}
  raw, collapsed = collapse_skips(messages)

  take_w = 0.0
  for m in voters:
    if m.vote != "take":
      continue
    take_w += float(wmap.get(m.agent, m.weight if m.weight else 1.0))

  # Correlated skips → one weight = max of group; others add individually
  skip_w = 0.0
  corr = [m for m in voters if m.vote == "skip" and m.agent in _CORRELATED]
  others = [m for m in voters if m.vote == "skip" and m.agent not in _CORRELATED]
  if corr:
    skip_w += max(float(wmap.get(m.agent, m.weight if m.weight else 1.0)) for m in corr)
  for m in others:
    skip_w += float(wmap.get(m.agent, m.weight if m.weight else 1.0))

  denom = take_w + skip_w
  score = take_w / denom if denom else 0.0

  hard: set[str] = set()
  for m in messages:
    if m.vote != "skip":
      continue
    if m.agent == "Cost":
      hard.add("Cost")
    elif m.agent == "MetaLabel" and bool((m.payload or {}).get("hard")):
      hard.add("MetaLabel")
    elif m.agent == "RulesClerk" and bool((m.payload or {}).get("hard")):
      hard.add("RulesClerk")
    # Decay / JumpRisk stay weighted votes only — hard Decay caused a cash death spiral.
  tradeable = score >= tau and not hard
  reason = "ok" if tradeable else f"score={score:.2f}|skips={collapsed}|hard={sorted(hard)}"
  return Agreement(
    score=round(score, 4),
    tradeable=tradeable,
    collapsed_votes=collapsed,
    raw_skip_votes=raw,
    tau=tau,
    reason=reason,
  )


def pick_expert(
  *,
  tradeable: bool,
  ecology: str = "nse",
  preferred: str = "orwidth_orb",
) -> Allocation:
  expert = preferred if tradeable else "cash"
  assert_no_cross_softmax(ecology, [expert])  # type: ignore[arg-type]
  return Allocation(size_mult=1.0 if tradeable else 0.0, expert=expert, notes=("supervisor",))
