"""Kyle-λ lite proxy — price impact per unit volume from OHLCV.

True Kyle needs quotes / order flow. We use |Δp| / √volume as a trainable λ proxy.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from processor.hybrid.recognition.types import AgentMessage


def _kyle_lambda(bars: Sequence[dict[str, Any]], *, n: int = 16) -> float | None:
  if len(bars) < 5:
    return None
  chunk = list(bars)[-n:]
  impacts: list[float] = []
  for i in range(1, len(chunk)):
    c0 = float(chunk[i - 1].get("close") or 0)
    c1 = float(chunk[i].get("close") or 0)
    vol = float(chunk[i].get("volume") or 0)
    if c0 <= 0 or vol <= 0:
      continue
    dp = abs(c1 / c0 - 1.0)
    impacts.append(dp / np.sqrt(vol))
  if len(impacts) < 3:
    return None
  return float(np.median(impacts))


def kyle_message(
  bars: Sequence[dict[str, Any]] | None = None,
  *,
  high_lambda_q: float = 0.0,
  **_: object,
) -> AgentMessage:
  if not bars:
    return AgentMessage(agent="Kyle", vote="annotate", status="insufficient_data", reason="needs_quotes")

  lam = _kyle_lambda(bars)
  if lam is None:
    return AgentMessage(agent="Kyle", vote="annotate", status="insufficient_data", reason="no_volume")

  # Adaptive threshold from recent path — high λ = costly to trade
  closes = [float(b.get("close") or 0) for b in bars[-20:]]
  vols = [float(b.get("volume") or 0) for b in bars[-20:]]
  sample = []
  for i in range(1, len(closes)):
    if closes[i - 1] > 0 and vols[i] > 0:
      sample.append(abs(closes[i] / closes[i - 1] - 1.0) / np.sqrt(vols[i]))
  thr = float(np.percentile(sample, 75)) if len(sample) >= 4 else lam * 1.2
  if high_lambda_q > 0:
    thr = high_lambda_q

  payload = {"proxy": "ohlcv_kyle_lambda", "lambda": round(lam, 10), "threshold": round(thr, 10)}
  if lam >= thr * 1.15:
    return AgentMessage(agent="Kyle", vote="skip", reason="proxy_high_impact", payload=payload, status="ok")
  if lam <= thr * 0.7:
    return AgentMessage(agent="Kyle", vote="take", reason="proxy_cheap_impact", payload=payload, status="ok")
  return AgentMessage(agent="Kyle", vote="annotate", reason="proxy_mid_impact", payload=payload, status="ok")
