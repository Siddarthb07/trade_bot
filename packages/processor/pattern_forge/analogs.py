"""Historical analog matching — expanding-window only (strictly before asof)."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from processor.hybrid.recognition.swarm.similarity import dtw_distance


def _z(x: np.ndarray) -> np.ndarray:
  s = float(x.std())
  if s < 1e-12:
    return x - x.mean()
  return (x - x.mean()) / s


def euclidean_z(a: Sequence[float], b: Sequence[float]) -> float:
  x = _z(np.asarray(a, dtype=float))
  y = _z(np.asarray(b, dtype=float))
  n = min(len(x), len(y))
  if n < 4:
    return float("inf")
  return float(np.linalg.norm(x[-n:] - y[-n:]))


def find_analogs(
  query: Sequence[float],
  library: Sequence[dict[str, Any]],
  *,
  k: int = 8,
  metric: str = "dtw",
  max_dist: float = 12.0,
) -> list[dict[str, Any]]:
  """library items: {id, path: list[float], forward_ret: float} — all pre-asof."""
  if len(query) < 4 or not library:
    return []
  scored: list[dict[str, Any]] = []
  for row in library:
    path = row.get("path") or []
    if len(path) < 4:
      continue
    if metric == "euclidean":
      d = euclidean_z(query, path)
    else:
      d = dtw_distance(query, path)
    if d > max_dist:
      continue
    scored.append(
      {
        "id": row.get("id"),
        "distance": d,
        "forward_ret": float(row.get("forward_ret") or 0.0),
        "side_hint": row.get("side_hint"),
      }
    )
  scored.sort(key=lambda r: r["distance"])
  return scored[: max(1, int(k))]


def analog_signal(
  query: Sequence[float],
  library: Sequence[dict[str, Any]],
  *,
  k: int = 8,
  min_mean_abs: float = 0.002,
  long_thresh: float = 0.003,
  short_thresh: float = -0.003,
) -> dict[str, Any]:
  """Mean forward return of k nearest analogs → buy/sell/flat."""
  hits = find_analogs(query, library, k=k)
  if len(hits) < 3:
    return {
      "side": "flat",
      "confidence": 0.5,
      "reason": "insufficient_analogs",
      "n": len(hits),
      "mean_fwd": None,
      "analogs": hits,
    }
  mean_fwd = float(np.mean([h["forward_ret"] for h in hits]))
  if abs(mean_fwd) < min_mean_abs:
    return {
      "side": "flat",
      "confidence": 0.5,
      "reason": "weak_analog_edge",
      "n": len(hits),
      "mean_fwd": mean_fwd,
      "analogs": hits,
    }
  if mean_fwd >= long_thresh:
    side = "buy"
  elif mean_fwd <= short_thresh:
    side = "sell"
  else:
    side = "flat"
  conf = min(0.85, 0.52 + abs(mean_fwd) * 8.0)
  return {
    "side": side,
    "confidence": float(conf),
    "reason": f"analog_mean_fwd={mean_fwd:.4f}",
    "n": len(hits),
    "mean_fwd": mean_fwd,
    "analogs": hits,
  }


def build_library_from_paths(
  paths: Sequence[Sequence[float]],
  forward_rets: Sequence[float],
  *,
  prefix: str = "a",
) -> list[dict[str, Any]]:
  out = []
  for i, (p, fr) in enumerate(zip(paths, forward_rets)):
    out.append({"id": f"{prefix}{i}", "path": list(p), "forward_ret": float(fr)})
  return out
