"""WhatsApp message templates."""

from __future__ import annotations

from datetime import datetime, timedelta
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
    "horizon_label": dist.get("sell_horizon_label"),
    "horizon_days": dist.get("sell_horizon_days"),
  }


def _sell_line(meta: dict, disclosed_at: datetime | None = None) -> str:
  label = meta.get("horizon_label")
  days = meta.get("horizon_days")
  exp = meta.get("expected_pct")
  parts: list[str] = []
  if exp is not None:
    parts.append(f"Est. +{exp * 100:.0f}%")
  if label:
    parts.append(f"Hold {label}")
  if days and disclosed_at:
    sell_by = (disclosed_at.astimezone(IST) + timedelta(days=int(days))).strftime("%d %b")
    parts.append(f"Exit ~{sell_by}")
  return " · ".join(parts) if parts else ""


def _link_block(url: str) -> list[str]:
  """URL on its own line, column 0 — required for WhatsApp full-link tap."""
  return ["", url]


def brief_whatsapp_message(signal: Signal, score: SignalScore, dashboard_url: str) -> str:
  emoji = TIER_EMOJI.get(score.tier, "⚪")
  meta = _score_meta(score)
  prob = meta.get("prob")
  prob_text = f"{prob * 100:.0f}% conf" if prob is not None else ""
  sell = _sell_line(meta, signal.disclosed_at)
  source_label = signal.source.replace("nse_", "").replace("sec_", "").upper()
  link = signal_dashboard_url(str(signal.id), dashboard_url)
  lines = [
    f"{emoji} {score.tier} · {signal.market} · {signal.ticker} · {signal.action}",
    f"{source_label} · {format_currency(signal.value, signal.market)} · {prob_text}",
  ]
  if sell:
    lines.append(sell)
  lines.extend(_link_block(link))
  return "\n".join(lines)[:900]


def daily_picks_message(
  picks: list[tuple[Signal, SignalScore]],
  dashboard_url: str,
  *,
  market: str = "IN",
  theme_picks: list[tuple[Signal, SignalScore]] | None = None,
) -> str:
  today = datetime.now(IST).strftime("%d %b")
  home = dashboard_home_url(dashboard_url)
  if not picks:
    lines_empty = [f"Smart Money · {today}", "No high-conviction BUY picks today."]
    lines_empty.extend(_link_block(home))
    return "\n".join(lines_empty)

  lines = [f"Smart Money · Top {len(picks)} Picks · {today} · {market} (by est. return)"]
  for idx, (signal, score) in enumerate(picks, start=1):
    meta = _score_meta(score)
    prob = meta.get("prob")
    exp = meta.get("expected_pct")
    prob_text = f"{prob * 100:.0f}%" if prob is not None else "—"
    exp_text = f"+{exp * 100:.0f}%" if exp is not None else "—"
    sell = _sell_line(meta, signal.disclosed_at)
    entity_short = signal.entity[:28] + "…" if len(signal.entity) > 30 else signal.entity
    link = signal_dashboard_url(str(signal.id), dashboard_url)
    lines.append(
      f"\n{idx}. {TIER_EMOJI.get(score.tier, '⚪')} {signal.ticker} · BUY · "
      f"{format_currency(signal.value, signal.market)} · Est {exp_text}"
    )
    if sell:
      lines.append(f"   {sell} · {prob_text} conf")
    lines.append(f"   {entity_short}")
    lines.extend(_link_block(link))

  if theme_picks:
    lines.append(f"\n🌍 World-demand themes ({len(theme_picks)} picks)")
    for idx, (signal, score) in enumerate(theme_picks, start=1):
      meta = _score_meta(score)
      prob = meta.get("prob")
      exp = meta.get("expected_pct")
      prob_text = f"{prob * 100:.0f}%" if prob is not None else "—"
      exp_text = f"+{exp * 100:.0f}%" if exp is not None else "—"
      sell = _sell_line(meta, signal.disclosed_at)
      raw = signal.raw_json or {}
      theme_name = raw.get("theme_name") or signal.entity
      theme_short = theme_name[:32] + "…" if len(theme_name) > 34 else theme_name
      link = signal_dashboard_url(str(signal.id), dashboard_url)
      lines.append(
        f"\nT{idx}. {TIER_EMOJI.get(score.tier, '⚪')} {signal.ticker} · {signal.market} · Est {exp_text}"
      )
      lines.append(f"   {theme_short} · {prob_text} conf")
      if sell:
        lines.append(f"   {sell}")
      lines.extend(_link_block(link))

  lines.append("\nSame WiFi as PC. Not investment advice.")
  lines.extend(_link_block(home))
  return "\n".join(lines)[:3500]


def digest_message(count: int, summary: str, dashboard_url: str) -> str:
  home = dashboard_home_url(dashboard_url)
  lines = [f"US Digest · {count} new 13F filings", summary]
  lines.extend(_link_block(home))
  return "\n".join(lines)[:400]
