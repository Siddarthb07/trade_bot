"""Ecology split — NSE product vs crypto/meme research. Never mix softmaxes."""

from __future__ import annotations

from typing import Iterable

from processor.hybrid.recognition.types import Ecology

NSE_EXPERTS = frozenset(
  {
    "orwidth_orb",
    "adaptive_edge",
    "copy_bulk_pro",
    "pattern_candle",
    "pattern_analog",
    "orb_two_sided",
    "hybrid_stock_market",
    "cash",
  }
)
CRYPTO_EXPERTS = frozenset({"momentum_attention", "cash"})
MEME_EXPERTS = frozenset({"cash"})  # research-only; no product experts


def experts_for(ecology: Ecology) -> frozenset[str]:
  if ecology == "nse":
    return NSE_EXPERTS
  if ecology == "crypto":
    return CRYPTO_EXPERTS
  return MEME_EXPERTS


def assert_no_cross_softmax(ecology: Ecology, picked: Iterable[str]) -> None:
  allowed = experts_for(ecology)
  bad = [p for p in picked if p not in allowed]
  if bad:
    raise ValueError(f"ecology={ecology} forbids experts {bad}; allowed={sorted(allowed)}")
