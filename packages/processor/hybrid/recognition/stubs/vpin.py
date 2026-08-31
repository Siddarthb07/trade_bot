"""VPIN-lite proxy from OHLCV bars (Easley et al. spirit — volume-bucket toxicity).

True VPIN needs trade-classified volume buckets. On NSE 5m OHLCV we use signed
volume imbalance as a trainable proxy so the agent can vote and learn.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from processor.hybrid.recognition.types import AgentMessage


def _signed_volume_imbalance(bars: Sequence[dict[str, Any]], *, n: int = 20) -> float | None:
  if len(bars) < 4:
    return None
  chunk = list(bars)[-n:]
  signed = 0.0
  total = 0.0
  for b in chunk:
    vol = float(b.get("volume") or 0)
    o = float(b.get("open") or 0)
    c = float(b.get("close") or 0)
    if vol <= 0 or o <= 0:
      continue
    sign = 1.0 if c >= o else -1.0
    signed += sign * vol
    total += vol
  if total <= 0:
    return None
  return float(signed / total)


def vpin_message(
  bars: Sequence[dict[str, Any]] | None = None,
  *,
  toxicity_thresh: float = 0.55,
  **_: object,
) -> AgentMessage:
  if not bars:
    return AgentMessage(agent="VPIN", vote="annotate", status="insufficient_data", reason="needs_volume_buckets")

  imb = _signed_volume_imbalance(bars)
  if imb is None:
    return AgentMessage(agent="VPIN", vote="annotate", status="insufficient_data", reason="no_volume")

  tox = abs(imb)
  payload = {"proxy": "ohlcv_signed_imbalance", "imbalance": round(imb, 4), "toxicity": round(tox, 4)}
  if tox >= toxicity_thresh and imb < 0:
    return AgentMessage(
      agent="VPIN",
      vote="skip",
      reason="proxy_toxic_sell_imbalance",
      payload=payload,
      status="ok",
    )
  if tox >= toxicity_thresh and imb > 0:
    return AgentMessage(
      agent="VPIN",
      vote="take",
      reason="proxy_buy_flow",
      payload=payload,
      status="ok",
    )
  return AgentMessage(
    agent="VPIN",
    vote="annotate",
    reason="proxy_balanced",
    payload=payload,
    status="ok",
  )
