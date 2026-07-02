"""WhatsApp message templates."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.models import Signal, SignalScore
from notifier.links import dashboard_home_url, signal_dashboard_url

IST = ZoneInfo("Asia/Kolkata")
TIER_EMOJI = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}


def format_currency(value: float | None, market: str) -> str:
  if value is None:
    return "—"
  if market == "IN":
    if value >= 1e7:
      return f"₹{value / 1e7:.1f}Cr"
    if value >= 1e5:
      return f"₹{value / 1e5:.1f}L"
    return f"₹{value:,.0f}"
  if value >= 1e9:
    return f"${value / 1e9:.1f}B"
  if value >= 1e6:
    return f"${value / 1e6:.1f}M"
  return f"${value:,.0f}"


def _score_meta(score: SignalScore) -> dict:
  dist = score.return_distribution or {}
  return {
    "prob": dist.get("calibrated_probability"),
    "expected_pct": dist.get("expected_return_pct"),
    "dist": dist,
  }


def _timeframe_lines(dist: dict) -> list[str]:
  lines: list[str] = []
  if dist.get("hold_label_long"):
    lines.append(f"HOLD: {dist['hold_label_long']}")
  elif dist.get("hold_days"):
    lines.append(f"HOLD: {dist['hold_days']} days")
  if dist.get("exit_date_full") or dist.get("exit_date_label"):
    lines.append(f"SELL BY: {dist.get('exit_date_full') or dist['exit_date_label']}")
  if dist.get("review_date_label"):
    lines.append(f"REVIEW: {dist['review_date_label']} (mid-hold)")
  return lines


def _sell_line(meta: dict) -> str:
  dist = meta.get("dist") or {}
  exp = meta.get("expected_pct")
  parts = _timeframe_lines(dist)
  if exp is not None:
    parts.append(f"Est +{exp * 100:.0f}%")
  return " · ".join(parts) if parts else ""


def _link_block(url: str, label: str = "Open") -> list[str]:
  """Label line + URL at column 0 (WhatsApp linkify-friendly)."""
  return [label, url]


def brief_whatsapp_message(signal: Signal, score: SignalScore, dashboard_url: str) -> str:
  emoji = TIER_EMOJI.get(score.tier, "⚪")
  meta = _score_meta(score)
  prob = meta.get("prob")
  prob_text = f"{prob * 100:.0f}% conf" if prob is not None else ""
  source_label = signal.source.replace("nse_", "").replace("sec_", "").upper()
  link = signal_dashboard_url(str(signal.id), dashboard_url)
  lines = [
    f"{emoji} {score.tier} · {signal.market} · {signal.ticker} · {signal.action}",
    f"{source_label} · {format_currency(signal.value, signal.market)} · {prob_text}",
  ]
  for tl in _timeframe_lines(meta["dist"]):
    lines.append(tl)
  lines.extend(_link_block(link))
  return "\n".join(lines)[:900]


def holdings_message(
  holdings: list[tuple[Signal, SignalScore]],
  dashboard_url: str,
  *,
  market: str = "IN",
) -> str:
  """Active holds with sell-by dates and tappable links."""
  today = datetime.now(IST).strftime("%d %b %Y")
  home = dashboard_home_url(dashboard_url)

  if not holdings:
    lines = [
      f"Trade Bot · Current holds · {today}",
      f"No active holds in {market} right now.",
      "Check dashboard for new picks.",
    ]
    lines.extend(_link_block(home, "Open dashboard"))
    return "\n".join(lines)

  lines = [f"Trade Bot · Current holds · {today} · {market}"]
  lines.append(f"{len(holdings)} stocks in active hold window\n")

  for idx, (signal, score) in enumerate(holdings, start=1):
    meta = _score_meta(score)
    dist = meta["dist"]
    prob = meta.get("prob")
    exp = meta.get("expected_pct")
    prob_text = f"{prob * 100:.0f}%" if prob is not None else "—"
    exp_text = f"+{exp * 100:.0f}%" if exp is not None else "—"
    link = signal_dashboard_url(str(signal.id), dashboard_url)

    kind = "Bulk" if signal.source in ("nse_bulk", "nse_block") else "Demand"
    if signal.source == "macro_theme":
      raw = signal.raw_json or {}
      kind = raw.get("theme_name") or "Demand"
      if len(kind) > 24:
        kind = kind[:22] + "…"

    status = dist.get("hold_status") or "active"
    status_label = {"active": "Holding", "review_due": "Review now", "exit_window": "Exit window"}.get(status, status)
    countdown = dist.get("countdown_label") or ""

    lines.append(
      f"\n{idx}. {TIER_EMOJI.get(score.tier, '⚪')} {signal.ticker} · {kind} · {status_label}"
    )
    for tl in _timeframe_lines(dist):
      lines.append(f"   {tl}")
    if countdown:
      lines.append(f"   {countdown}")
    lines.append(f"   Est {exp_text} · {prob_text} conf")
    if signal.source in ("nse_bulk", "nse_block") and signal.value:
      lines.append(f"   Deal {format_currency(signal.value, signal.market)}")
    lines.extend(_link_block(link))

  lines.append("\nNot investment advice. Same WiFi as PC.")
  lines.extend(_link_block(home, "Open dashboard"))
  return "\n".join(lines)[:4000]


def daily_picks_message(
  picks: list[tuple[Signal, SignalScore]],
  dashboard_url: str,
  *,
  market: str = "IN",
  theme_picks: list[tuple[Signal, SignalScore]] | None = None,
  bulk_deal_counts: dict[str, int] | None = None,
  bulk_deal_counts_week: dict[str, int] | None = None,
) -> str:
  today = datetime.now(IST).strftime("%d %b")
  home = dashboard_home_url(dashboard_url)
  if not picks:
    lines_empty = [f"Trade Bot · {today}", "No high-conviction BUY picks today."]
    lines_empty.extend(_link_block(home))
    return "\n".join(lines_empty)

  lines = [f"Trade Bot · Top {len(picks)} Picks · {today} · {market} (by est. return)"]
  for idx, (signal, score) in enumerate(picks, start=1):
    meta = _score_meta(score)
    prob = meta.get("prob")
    exp = meta.get("expected_pct")
    prob_text = f"{prob * 100:.0f}%" if prob is not None else "—"
    exp_text = f"+{exp * 100:.0f}%" if exp is not None else "—"
    entity_short = signal.entity[:28] + "…" if len(signal.entity) > 30 else signal.entity
    link = signal_dashboard_url(str(signal.id), dashboard_url)
    lines.append(
      f"\n{idx}. {TIER_EMOJI.get(score.tier, '⚪')} {signal.ticker} · BUY · "
      f"{format_currency(signal.value, signal.market)} · Est {exp_text}"
    )
    for tl in _timeframe_lines(meta["dist"]):
      lines.append(f"   {tl}")
    week_n = (bulk_deal_counts_week or {}).get(signal.ticker) or (bulk_deal_counts or {}).get(signal.ticker)
    if week_n and week_n > 1:
      lines.append(f"   {week_n} bulk deals this week")
    lines.append(f"   {prob_text} conf · {entity_short}")
    lines.extend(_link_block(link))

  if theme_picks:
    lines.append(f"\n🌍 World-demand themes ({len(theme_picks)} picks)")
    for idx, (signal, score) in enumerate(theme_picks, start=1):
      meta = _score_meta(score)
      prob = meta.get("prob")
      exp = meta.get("expected_pct")
      prob_text = f"{prob * 100:.0f}%" if prob is not None else "—"
      exp_text = f"+{exp * 100:.0f}%" if exp is not None else "—"
      raw = signal.raw_json or {}
      theme_name = raw.get("theme_name") or signal.entity
      theme_short = theme_name[:32] + "…" if len(theme_name) > 34 else theme_name
      link = signal_dashboard_url(str(signal.id), dashboard_url)
      lines.append(
        f"\nT{idx}. {TIER_EMOJI.get(score.tier, '⚪')} {signal.ticker} · {signal.market} · Est {exp_text}"
      )
      for tl in _timeframe_lines(meta["dist"]):
        lines.append(f"   {tl}")
      if meta["dist"].get("bulk_confirmed"):
        n = meta["dist"].get("bulk_deal_count") or 0
        lines.append(f"   Bulk confirmed · {n} deal(s) in 30d")
      lines.append(f"   {theme_short} · {prob_text} conf")
      lines.extend(_link_block(link))

  lines.append("\nSame WiFi as PC. Not investment advice.")
  lines.extend(_link_block(home))
  return "\n".join(lines)[:3500]


def digest_message(count: int, summary: str, dashboard_url: str) -> str:
  home = dashboard_home_url(dashboard_url)
  lines = [f"US Digest · {count} new 13F filings", summary]
  lines.extend(_link_block(home))
  return "\n".join(lines)[:400]
