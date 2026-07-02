"""Expected return + confidence with transparent breakdown."""

from __future__ import annotations

from typing import Any

from processor.fundamentals import fundamentals_score


def _clamp(v: float, lo: float, hi: float) -> float:
  return max(lo, min(hi, v))


def estimate_theme_returns(
  *,
  theme_heat: float,
  alignment: float,
  stock_trend: dict[str, Any],
  proxy_trend: dict[str, Any],
  fundamentals: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Stock-specific expected return — avoids identical caps for hot themes."""
  fund = fundamentals or {}
  fscore = fundamentals_score(fund)

  stock_1m = float(stock_trend.get("return_1m") or 0)
  stock_3m = float(stock_trend.get("return_3m") or 0)
  proxy_3m = float(proxy_trend.get("return_3m") or 0)
  rel_strength = stock_3m - proxy_3m
  vol = float(stock_trend.get("volatility_20d") or 0.28)

  momentum = stock_3m * 0.42 + stock_1m * 0.22 + rel_strength * 0.18
  theme = theme_heat * 0.06
  align = alignment * 0.28
  quality = (fscore - 0.5) * 0.12
  vol_penalty = max(0.0, vol - 0.32) * 0.08

  expected = 0.035 + momentum + theme + align + quality - vol_penalty
  # Dynamic cap so high-momentum peers (e.g. MU vs WDC) don't all flatten to the same %
  cap = 0.36 + min(0.22, abs(stock_3m) * 0.06 + abs(rel_strength) * 0.10 + fscore * 0.08)
  expected = _clamp(expected, 0.04, cap)

  prob = 0.40 + theme_heat * 0.10 + alignment * 0.35 + fscore * 0.12
  if stock_1m > 0.03:
    prob += 0.05
  elif stock_1m < -0.05:
    prob -= 0.06
  if stock_trend.get("above_ma50"):
    prob += 0.03
  else:
    prob -= 0.02
  prob = _clamp(prob, 0.34, 0.84)

  rationale_parts = []
  if abs(stock_3m) > 0.01:
    rationale_parts.append(f"3mo price {stock_3m * 100:+.1f}%")
  if abs(rel_strength) > 0.01:
    rationale_parts.append(f"vs theme proxy {rel_strength * 100:+.1f}%")
  pe = fund.get("trailing_pe")
  if pe is not None:
    rationale_parts.append(f"P/E {pe:.1f}")
  pm = fund.get("profit_margin")
  if pm is not None:
    rationale_parts.append(f"net margin {pm * 100:.1f}%")
  rg = fund.get("revenue_growth")
  if rg is not None:
    rationale_parts.append(f"rev growth {rg * 100:+.1f}%")

  return {
    "expected_return_pct": round(expected, 4),
    "calibrated_probability": round(prob, 4),
    "return_breakdown": {
      "momentum_pct": round(momentum, 4),
      "theme_pct": round(theme, 4),
      "alignment_pct": round(align, 4),
      "fundamentals_pct": round(quality, 4),
      "volatility_penalty_pct": round(vol_penalty, 4),
      "relative_strength_3m": round(rel_strength, 4),
      "fundamentals_score": round(fscore, 3),
    },
    "return_rationale": "; ".join(rationale_parts) if rationale_parts else "Rule-based theme + trend blend",
  }


def estimate_bulk_returns(
  *,
  median_return: float | None,
  win_rate: float | None,
  return_1m: float | None,
  return_3m: float | None,
  cluster_count: int,
  fundamentals: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Bulk deal expected return from investor history + momentum + fundamentals."""
  fund = fundamentals or {}
  fscore = fundamentals_score(fund)
  med = float(median_return or 0.06)
  wr = float(win_rate or 0.5)
  r1 = float(return_1m or 0)
  r3 = float(return_3m or 0)

  hist = med * 0.55
  momentum = r1 * 0.18 + r3 * 0.12
  cluster = 0.025 if cluster_count >= 2 else 0.0
  quality = (fscore - 0.5) * 0.06

  expected = hist + momentum + cluster + quality
  if wr < 0.48:
    expected *= 0.88
  expected = _clamp(expected, 0.03, 0.42)

  prob = 0.38 + wr * 0.35 + (0.06 if cluster_count >= 2 else 0) + fscore * 0.08
  if r1 > 0.05:
    prob += 0.04
  prob = _clamp(prob, 0.32, 0.88)

  return {
    "expected_return_pct": round(expected, 4),
    "calibrated_probability": round(prob, 4),
    "return_breakdown": {
      "investor_history_pct": round(hist, 4),
      "momentum_pct": round(momentum, 4),
      "cluster_pct": round(cluster, 4),
      "fundamentals_pct": round(quality, 4),
      "fundamentals_score": round(fscore, 3),
    },
    "return_rationale": f"Investor median {med * 100:.1f}%; win rate {wr * 100:.0f}%; 1mo {r1 * 100:+.1f}%",
  }
