"""Lightweight 3-state Gaussian HMM on returns — filtered posteriors only (no smoother).

Uses a fixed emission prior + forward filter. Not a full EM fit — cold-start safe.
Hamilton 1989 filtered probabilities; never use smoothed P for live decisions.
"""

from __future__ import annotations

import numpy as np

from processor.hybrid.recognition.types import RegimePosterior


# emission means / stds for (trend, chop, risk_off) on daily-ish returns
_MU = np.array([0.004, 0.0, -0.008], dtype=float)
_SIG = np.array([0.008, 0.012, 0.02], dtype=float)
_TRANS = np.array(
  [
    [0.90, 0.08, 0.02],
    [0.10, 0.80, 0.10],
    [0.05, 0.15, 0.80],
  ],
  dtype=float,
)


def _gauss_ll(x: float, mu: float, sig: float) -> float:
  z = (x - mu) / max(sig, 1e-9)
  return float(-0.5 * z * z - np.log(max(sig, 1e-9)) - 0.5 * np.log(2 * np.pi))


def filtered_regime(closes: list[float] | np.ndarray) -> RegimePosterior:
  arr = np.asarray(closes, dtype=float)
  if len(arr) < 20:
    return RegimePosterior(status="cold_start", label="unknown")

  rets = np.diff(arr) / np.maximum(arr[:-1], 1e-12)
  # use last 60 returns max
  rets = rets[-60:]
  alpha = np.ones(3) / 3.0
  for r in rets:
    emit = np.array([_gauss_ll(float(r), _MU[i], _SIG[i]) for i in range(3)])
    # numerically stable: work in log space lightly via max
    pred = alpha @ _TRANS
    unnorm = pred * np.exp(emit - emit.max())
    s = unnorm.sum()
    alpha = unnorm / s if s > 0 else pred

  p_trend, p_chop, p_risk = (float(x) for x in alpha)
  labels = ["trend", "chop", "risk_off"]
  label = labels[int(np.argmax(alpha))]
  return RegimePosterior(
    p_trend=round(p_trend, 4),
    p_chop=round(p_chop, 4),
    p_risk_off=round(p_risk, 4),
    label=label,
    status="ok",
  )


def filtered_at_t(closes: list[float], t: int) -> RegimePosterior:
  """Causal slice: only closes[: t+1]."""
  if t < 0:
    return RegimePosterior(status="missing", label="unknown")
  return filtered_regime(closes[: t + 1])
