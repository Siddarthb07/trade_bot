"""DTW / shapelet-lite similarity agent (Ye & Keogh)."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from processor.hybrid.recognition.types import AgentMessage


def _z(x: np.ndarray) -> np.ndarray:
  s = float(x.std())
  if s < 1e-12:
    return x - x.mean()
  return (x - x.mean()) / s


def dtw_distance(a: Sequence[float], b: Sequence[float]) -> float:
  x = _z(np.asarray(a, dtype=float))
  y = _z(np.asarray(b, dtype=float))
  n, m = len(x), len(y)
  if n == 0 or m == 0:
    return float("inf")
  dp = np.full((n + 1, m + 1), np.inf)
  dp[0, 0] = 0.0
  for i in range(1, n + 1):
    for j in range(1, m + 1):
      cost = abs(float(x[i - 1] - y[j - 1]))
      dp[i, j] = cost + min(dp[i - 1, j], dp[i, j - 1], dp[i - 1, j - 1])
  return float(dp[n, m])


def similarity_message(
  path: Sequence[float],
  templates: dict[str, Sequence[float]],
  *,
  hit_rates: dict[str, float] | None = None,
  max_dist: float = 8.0,
) -> AgentMessage:
  if len(path) < 4 or not templates:
    return AgentMessage(agent="Similarity", vote="annotate", status="cold_start", reason="no_templates")

  best_id = None
  best_d = float("inf")
  for tid, tmpl in templates.items():
    d = dtw_distance(path, tmpl)
    if d < best_d:
      best_d = d
      best_id = tid

  hr = (hit_rates or {}).get(best_id or "", 0.5)
  if best_d > max_dist:
    return AgentMessage(
      agent="Similarity",
      vote="skip",
      reason=f"no_analog_d={best_d:.2f}",
      payload={"distance": best_d, "analog_id": best_id, "hit_rate": hr},
      status="ok",
    )
  vote = "take" if hr >= 0.55 else "skip"
  return AgentMessage(
    agent="Similarity",
    vote=vote,
    reason=f"analog={best_id}|d={best_d:.2f}|hr={hr:.2f}",
    payload={"distance": best_d, "analog_id": best_id, "hit_rate": hr},
    status="ok",
  )


DEFAULT_TEMPLATES: dict[str, list[float]] = {
  "trend_up": [100 + i * 0.4 for i in range(24)],
  "failed_break": [100, 101, 102, 101.5, 100.5, 99.5, 99.0, 98.5] + [98.2] * 16,
  "chop": [100 + (0.3 if i % 2 == 0 else -0.3) for i in range(24)],
}

DEFAULT_HIT_RATES = {"trend_up": 0.62, "failed_break": 0.28, "chop": 0.40}
