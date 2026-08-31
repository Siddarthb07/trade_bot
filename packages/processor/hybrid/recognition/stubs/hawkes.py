"""Hawkes-lite proxy — self-exciting intensity of large |returns| on OHLCV path.

True Hawkes needs event times. We use a trainable excitation score from bar returns.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from processor.hybrid.recognition.types import AgentMessage


def _excitation(bars: Sequence[dict[str, Any]], *, n: int = 24) -> tuple[float, float] | None:
  if len(bars) < 6:
    return None
  closes = np.asarray([float(b.get("close") or 0) for b in bars[-n:]], dtype=float)
  if np.any(closes <= 0):
    return None
  r = np.diff(np.log(closes))
  if len(r) < 4:
    return None
  thr = float(np.std(r) * 1.5) if float(np.std(r)) > 1e-12 else 0.002
  events = np.abs(r) >= thr
  # Decaying sum of past events (Hawkes-like)
  intensity = 0.0
  for i, hit in enumerate(events):
    if hit:
      age = len(events) - 1 - i
      intensity += float(np.exp(-0.15 * age))
  rate = float(np.mean(events))
  return intensity, rate


def hawkes_message(
  *,
  ecology: str = "nse",
  bars: Sequence[dict[str, Any]] | None = None,
  **_: object,
) -> AgentMessage:
  if ecology in ("crypto", "meme") and not bars:
    return AgentMessage(agent="Hawkes", vote="annotate", status="missing", reason="needs_event_times")
  if not bars:
    return AgentMessage(agent="Hawkes", vote="annotate", status="insufficient_data", reason="nse_ohlcv_only")

  out = _excitation(bars)
  if out is None:
    return AgentMessage(agent="Hawkes", vote="annotate", status="insufficient_data", reason="short_path")

  intensity, rate = out
  payload = {"proxy": "ohlcv_excitation", "intensity": round(intensity, 4), "event_rate": round(rate, 4)}
  # High self-excitation after sell shocks → skip; mild buy clustering → take
  last = bars[-1]
  prev = bars[-2] if len(bars) >= 2 else last
  last_ret = float(last.get("close") or 0) / max(float(prev.get("close") or 1), 1e-9) - 1.0
  if intensity >= 2.5 and last_ret < 0:
    return AgentMessage(agent="Hawkes", vote="skip", reason="proxy_cascade_down", payload=payload, status="ok")
  if 0.8 <= intensity <= 2.2 and last_ret > 0:
    return AgentMessage(agent="Hawkes", vote="take", reason="proxy_mild_excitation_up", payload=payload, status="ok")
  return AgentMessage(agent="Hawkes", vote="annotate", reason="proxy_quiet", payload=payload, status="ok")
