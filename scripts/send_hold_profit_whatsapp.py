#!/usr/bin/env python3
"""Send combined hold plan + profit outlook to WhatsApp."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc

from core.config import get_settings
from core.db import SessionLocal
from core.models import Signal, SignalScore
from notifier.holdings import _collect_holdings
from notifier.links import dashboard_home_url, signal_dashboard_url
from notifier.templates import TIER_EMOJI, _score_meta, _timeframe_lines, format_currency
from notifier.waha import send_whatsapp, waha_healthy
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
settings = get_settings()


def _latest_score(db, signal_id) -> SignalScore | None:
  return (
    db.query(SignalScore)
    .filter(SignalScore.signal_id == signal_id)
    .order_by(desc(SignalScore.scored_at))
    .first()
  )


def _top_profit_picks(db, market: str, limit: int = 5) -> list[tuple[Signal, SignalScore]]:
  since = datetime.now(timezone.utc) - timedelta(days=14)
  ranked: list[tuple[float, Signal, SignalScore]] = []

  bulk = (
    db.query(Signal)
    .filter(
      Signal.market == market,
      Signal.disclosed_at >= since,
      Signal.source.in_(["nse_bulk", "nse_block"]),
      Signal.action.in_(["BUY", "P", "A"]),
    )
    .all()
  )
  for signal in bulk:
    score = _latest_score(db, signal.id)
    if not score:
      continue
    dist = score.return_distribution or {}
    exp = dist.get("expected_return_pct")
    if exp is None:
      continue
    ranked.append((float(exp), signal, score))

  if settings.macro_themes_enabled:
    from processor.macro_themes import rank_all_picks

    for pick in rank_all_picks(market=market, min_composite=0.08)[:20]:
      signal = (
        db.query(Signal)
        .filter(
          Signal.source == "macro_theme",
          Signal.ticker == pick["ticker"],
          Signal.market == pick["market"],
        )
        .order_by(desc(Signal.disclosed_at))
        .first()
      )
      if not signal:
        continue
      score = _latest_score(db, signal.id)
      if not score:
        continue
      exp = pick.get("expected_return_pct") or (score.return_distribution or {}).get("expected_return_pct")
      if exp is None:
        continue
      ranked.append((float(exp), signal, score))

  ranked.sort(key=lambda x: x[0], reverse=True)
  best: dict[str, tuple[Signal, SignalScore]] = {}
  order: list[str] = []
  for _, signal, score in ranked:
    key = f"{signal.market}:{signal.ticker}"
    if key in best:
      continue
    best[key] = (signal, score)
    order.append(key)
    if len(order) >= limit:
      break
  return [best[k] for k in order]


def build_hold_profit_message(db, market: str = "IN") -> str:
  today = datetime.now(IST).strftime("%d %b %Y")
  url = settings.dashboard_public_url.rstrip("/")
  home = dashboard_home_url(url)
  holdings = _collect_holdings(db, market, 5)
  profits = _top_profit_picks(db, market, 5)

  lines = [
    f"Trade Bot · Top stocks · {today} · {market}",
    "",
    "HOLD PLAN — when to review & sell",
  ]

  if holdings:
    for idx, (signal, score) in enumerate(holdings, 1):
      meta = _score_meta(score)
      dist = meta["dist"]
      kind = "Bulk" if signal.source in ("nse_bulk", "nse_block") else "Demand"
      lines.append(f"\n{idx}. {TIER_EMOJI.get(score.tier, '⚪')} {signal.ticker} · {kind}")
      for tl in _timeframe_lines(dist):
        lines.append(f"   {tl}")
      if dist.get("countdown_label"):
        lines.append(f"   {dist['countdown_label']}")
      lines.append(f"   {signal_dashboard_url(str(signal.id), url)}")
  else:
    lines.append("No active holds in window — see profit picks below.")

  lines.extend(["", "PROFIT OUTLOOK — est. returns"])
  if profits:
    for idx, (signal, score) in enumerate(profits, 1):
      meta = _score_meta(score)
      dist = meta["dist"]
      prob = meta.get("prob")
      exp = meta.get("expected_pct")
      prob_text = f"{prob * 100:.0f}%" if prob is not None else "—"
      exp_text = f"+{exp * 100:.0f}%" if exp is not None else "—"
      kind = "Bulk" if signal.source in ("nse_bulk", "nse_block") else "Demand"
      lines.append(f"\n{idx}. {TIER_EMOJI.get(score.tier, '⚪')} {signal.ticker} · {kind} · Est {exp_text}")
      for tl in _timeframe_lines(dist):
        lines.append(f"   {tl}")
      lines.append(f"   {prob_text} conf · {format_currency(signal.value, signal.market)}")
      lines.append(f"   {signal_dashboard_url(str(signal.id), url)}")
  else:
    lines.append("No scored picks in the last 14 days.")

  lines.extend(["", "Not investment advice. Same WiFi as PC.", home])
  return "\n".join(lines)[:4000]


def main() -> None:
  db = SessionLocal()
  try:
    text = build_hold_profit_message(db, "IN")
    if not waha_healthy():
      print("WAHA not healthy")
      return
    ok = send_whatsapp(text)
    print("sent", ok)
    print(text[:500], "...")
  finally:
    db.close()


if __name__ == "__main__":
  main()
