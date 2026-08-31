"""TickerChooser — rank universe candidates for a strategy."""

from __future__ import annotations

from typing import Any

from processor.day_sim import IN_UNIVERSE, IN_UNIVERSE_VOLATILE, US_UNIVERSE, US_UNIVERSE_VOLATILE
from processor.intraday_bars import default_open_range_bars, fetch_intraday_bars, pick_interval_for_date
from processor.strategies import session_or_breakout


def universe_for(market: str, *, volatile: bool = True) -> list[str]:
  m = market.upper()
  if m == "IN":
    return list(IN_UNIVERSE_VOLATILE if volatile else IN_UNIVERSE)
  return list(US_UNIVERSE_VOLATILE if volatile else US_UNIVERSE)


def rank_tickers(
  *,
  asof: str,
  market: str = "IN",
  strategy_id: str = "orwidth_orb",
  conf_floor: float = 0.48,
  min_or_pct: float = 0.0015,
  bar_interval: str = "auto",
  top_n: int = 24,
) -> list[dict[str, Any]]:
  """Score full volatile universe; return dense decision rows."""
  preferred = bar_interval if bar_interval != "auto" else "5m"
  interval = pick_interval_for_date(asof, preferred)
  or_bars = default_open_range_bars(interval)
  rows: list[dict[str, Any]] = []
  for ticker in universe_for(market, volatile=True):
    try:
      bars = fetch_intraday_bars(ticker, session_date=asof, interval=interval, market=market)
    except Exception as e:  # noqa: BLE001
      rows.append(
        {
          "ticker": ticker,
          "score": 0.0,
          "reason": f"fetch_error:{e}",
          "eligible": False,
          "rank": None,
          "interval": interval,
        }
      )
      continue
    if len(bars) < or_bars + 2:
      rows.append(
        {
          "ticker": ticker,
          "score": 0.0,
          "reason": "insufficient_bars",
          "eligible": False,
          "n_bars": len(bars),
          "interval": interval,
          "or_bars": or_bars,
        }
      )
      continue
    sob = session_or_breakout(bars, open_range_bars=or_bars)
    or_w = float(sob.get("or_width_pct") or 0)
    conf = float(sob.get("confidence") or 0)
    side = str(sob.get("side") or "flat")
    vol_score = float(sob.get("score") or 0)
    fail_reasons = []
    if side != "buy":
      fail_reasons.append(f"side={side}")
    if conf < conf_floor:
      fail_reasons.append(f"conf<{conf_floor}")
    if or_w < min_or_pct:
      fail_reasons.append(f"or_width<{min_or_pct}")
    eligible = not fail_reasons
    if strategy_id == "orwidth_orb":
      score = or_w * 100.0 + conf * 0.5 + vol_score * 0.1
    else:
      score = conf * 2.0 + vol_score
    rows.append(
      {
        "ticker": ticker,
        "score": round(score, 6),
        "or_width_pct": round(or_w, 6),
        "or_width_bps": round(or_w * 1e4, 2),
        "confidence": round(conf, 4),
        "vol_score": round(vol_score, 4),
        "side": side,
        "eligible": eligible,
        "reject_reasons": fail_reasons,
        "reason": str(sob.get("reason") or ""),
        "entry_i": sob.get("entry_i"),
        "entry_px": sob.get("entry_px"),
        "or_high": sob.get("or_high"),
        "or_low": sob.get("or_low"),
        "n_bars": len(bars),
        "interval": interval,
        "or_bars": or_bars,
        "conf_floor": conf_floor,
        "min_or_pct": min_or_pct,
      }
    )
  rows.sort(key=lambda r: (r.get("eligible") is True, float(r.get("score") or 0)), reverse=True)
  for i, r in enumerate(rows, 1):
    r["rank"] = i
  return rows[:top_n]
