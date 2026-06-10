"""World-affairs / demand-theme stock picks (public data, rule-based — no LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.tickers import normalize_ticker
from processor.market_data import compute_trend_features

SOURCE = "macro_theme"


@dataclass(frozen=True)
class ThemeStock:
  ticker: str
  market: str
  name: str


@dataclass(frozen=True)
class MacroTheme:
  slug: str
  name: str
  demand_driver: str
  world_context: str
  proxy_ticker: str
  stocks: tuple[ThemeStock, ...] = field(default_factory=tuple)


THEMES: tuple[MacroTheme, ...] = (
  MacroTheme(
    slug="ai_storage_demand",
    name="AI & Data Storage Demand",
    demand_driver="AI training and cloud workloads are driving record demand for NAND/SSD and high-capacity storage.",
    world_context=(
      "Hyperscalers and AI labs are expanding data-centre capex; storage names like Western Digital (SanDisk) "
      "and peers have rallied on supply tightness and higher ASPs — similar to the 2024–26 memory up-cycle."
    ),
    proxy_ticker="WDC",
    stocks=(
      ThemeStock("WDC", "US", "Western Digital (SanDisk)"),
      ThemeStock("MU", "US", "Micron Technology"),
      ThemeStock("STX", "US", "Seagate Technology"),
      ThemeStock("NVDA", "US", "NVIDIA"),
      ThemeStock("NETWEB", "IN", "Netweb Technologies"),
      ThemeStock("REDINGTON", "IN", "Redington (distribution)"),
      ThemeStock("SYRMA", "IN", "Syrma SGS Technology"),
    ),
  ),
  MacroTheme(
    slug="semiconductor_ai_chips",
    name="Semiconductor & AI Chips",
    demand_driver="Global chip demand from AI accelerators, smartphones, and auto electrification.",
    world_context=(
      "Export controls and fab bottlenecks keep advanced-node supply constrained while AI capex rises — "
      "beneficiaries include foundry, fabless, and equipment names riding the SOXX cycle."
    ),
    proxy_ticker="SOXX",
    stocks=(
      ThemeStock("NVDA", "US", "NVIDIA"),
      ThemeStock("AMD", "US", "Advanced Micro Devices"),
      ThemeStock("AVGO", "US", "Broadcom"),
      ThemeStock("QCOM", "US", "Qualcomm"),
      ThemeStock("MOSCHIP", "IN", "Moschip Technologies"),
      ThemeStock("DATAPATTNS", "IN", "Data Patterns India"),
      ThemeStock("KEI", "IN", "KEI Industries"),
    ),
  ),
  MacroTheme(
    slug="defense_geopolitics",
    name="Defense & Geopolitics",
    demand_driver="Rising global defence budgets amid regional conflicts and border security needs.",
    world_context=(
      "NATO re-arming, Middle-East tensions, and India's Atmanirbhar defence push support order books "
      "for aerospace, shipbuilding, and electronics defence suppliers."
    ),
    proxy_ticker="ITA",
    stocks=(
      ThemeStock("LMT", "US", "Lockheed Martin"),
      ThemeStock("RTX", "US", "RTX Corp"),
      ThemeStock("NOC", "US", "Northrop Grumman"),
      ThemeStock("PLTR", "US", "Palantir"),
      ThemeStock("BEL", "IN", "Bharat Electronics"),
      ThemeStock("HAL", "IN", "Hindustan Aeronautics"),
      ThemeStock("MAZDOCK", "IN", "Mazagon Dock"),
      ThemeStock("COCHINSHIP", "IN", "Cochin Shipyard"),
    ),
  ),
  MacroTheme(
    slug="power_datacenters",
    name="Power for Data Centers",
    demand_driver="AI data centres need reliable baseload and grid upgrades — power generators benefit.",
    world_context=(
      "US utilities and independent power producers with nuclear/gas baseload are re-rating on AI power demand; "
      "India's grid expansion and renewable+thermal mix support NTPC-style names."
    ),
    proxy_ticker="VST",
    stocks=(
      ThemeStock("VST", "US", "Vistra Energy"),
      ThemeStock("CEG", "US", "Constellation Energy"),
      ThemeStock("NRG", "US", "NRG Energy"),
      ThemeStock("NTPC", "IN", "NTPC"),
      ThemeStock("TATAPOWER", "IN", "Tata Power"),
      ThemeStock("TORNTPOWER", "IN", "Torrent Power"),
      ThemeStock("JSWENERGY", "IN", "JSW Energy"),
    ),
  ),
  MacroTheme(
    slug="critical_minerals",
    name="Critical Minerals & Copper",
    demand_driver="EV, grid, and AI infrastructure need copper, zinc, and specialty minerals.",
    world_context=(
      "Mine supply lags demand growth; copper and iron-ore miners rally when China stimulus or "
      "global infra spend accelerates — India miners track global metal prices."
    ),
    proxy_ticker="COPX",
    stocks=(
      ThemeStock("FCX", "US", "Freeport-McMoRan"),
      ThemeStock("SCCO", "US", "Southern Copper"),
      ThemeStock("HINDCOPPER", "IN", "Hindustan Copper"),
      ThemeStock("NMDC", "IN", "NMDC"),
      ThemeStock("MOIL", "IN", "MOIL"),
      ThemeStock("HINDZINC", "IN", "Hindustan Zinc"),
    ),
  ),
  MacroTheme(
    slug="cybersecurity",
    name="Cybersecurity",
    demand_driver="Nation-state hacking, ransomware, and digitalisation increase security spend.",
    world_context=(
      "Corporate and government IT budgets allocate more to zero-trust and endpoint protection "
      "after high-profile breaches — secular tailwind for security software vendors."
    ),
    proxy_ticker="CIBR",
    stocks=(
      ThemeStock("CRWD", "US", "CrowdStrike"),
      ThemeStock("PANW", "US", "Palo Alto Networks"),
      ThemeStock("FTNT", "US", "Fortinet"),
      ThemeStock("QUICKHEAL", "IN", "Quick Heal"),
    ),
  ),
  MacroTheme(
    slug="india_infra_capex",
    name="India Infrastructure Capex",
    demand_driver="Government roads, railways, and urban infra push multi-year order books.",
    world_context=(
      "Union Budget capex, PM Gati Shakti, and railway electrification support EPC and construction "
      "names with visible 2–3 year backlogs."
    ),
    proxy_ticker="LT.NS",
    stocks=(
      ThemeStock("LT", "IN", "Larsen & Toubro"),
      ThemeStock("IRB", "IN", "IRB Infrastructure"),
      ThemeStock("RVNL", "IN", "Rail Vikas Nigam"),
      ThemeStock("IRCON", "IN", "Ircon International"),
      ThemeStock("PNCINFRA", "IN", "PNC Infratech"),
    ),
  ),
)


def get_theme(slug: str) -> MacroTheme | None:
  for theme in THEMES:
    if theme.slug == slug:
      return theme
  return None


def _clamp(value: float, lo: float, hi: float) -> float:
  return max(lo, min(hi, value))


def evaluate_pick(theme: MacroTheme, stock: ThemeStock) -> dict[str, Any]:
  """Score one stock against its theme using public price data only."""
  proxy = compute_trend_features(normalize_ticker(theme.proxy_ticker, "US" if "." not in theme.proxy_ticker else "IN"))
  ticker_norm = normalize_ticker(stock.ticker, stock.market)
  trend = compute_trend_features(ticker_norm)

  proxy_1m = float(proxy.get("return_1m") or 0)
  proxy_3m = float(proxy.get("return_3m") or 0)
  stock_1m = float(trend.get("return_1m") or 0)
  stock_3m = float(trend.get("return_3m") or 0)

  theme_heat = _clamp(proxy_3m / 0.12, 0, 1.0)
  if proxy_1m > 0.04:
    theme_heat = _clamp(theme_heat + 0.15, 0, 1.0)

  alignment = 0.0
  if proxy_3m > 0.02 and stock_3m > 0:
    alignment += 0.12
  if proxy_1m > 0.01 and stock_1m > 0:
    alignment += 0.08
  if trend.get("above_ma50") and proxy.get("above_ma50"):
    alignment += 0.06
  if trend.get("momentum") == "bullish" and proxy.get("momentum") in ("bullish", "neutral"):
    alignment += 0.05

  prob = 0.48 + theme_heat * 0.14 + alignment
  if trend.get("momentum") == "bullish":
    prob += 0.04
  elif trend.get("momentum") == "bearish":
    prob -= 0.07
  if not trend.get("above_ma50"):
    prob -= 0.03
  prob = _clamp(prob, 0.35, 0.78)

  expected = 0.05 + theme_heat * 0.14 + max(0.0, stock_3m) * 0.35 + alignment * 0.5
  expected = _clamp(expected, 0.04, 0.32)

  if theme_heat >= 0.65 and alignment >= 0.15:
    tier = "HIGH"
  elif theme_heat >= 0.35 or alignment >= 0.10:
    tier = "MEDIUM"
  else:
    tier = "LOW"

  days = 45 + int(theme_heat * 45)
  if theme.slug in ("defense_geopolitics", "india_infra_capex"):
    days += 15
  label = f"~{days // 7} weeks (theme cycle)"

  composite = theme_heat * 0.45 + alignment * 1.8 + (prob - 0.48)

  return {
    "theme_slug": theme.slug,
    "theme_name": theme.name,
    "demand_driver": theme.demand_driver,
    "world_context": theme.world_context,
    "ticker": stock.ticker,
    "market": stock.market,
    "company_name": stock.name,
    "theme_heat": round(theme_heat, 3),
    "alignment_score": round(alignment, 3),
    "composite_score": round(composite, 3),
    "calibrated_probability": round(prob, 4),
    "expected_return_pct": round(expected, 4),
    "tier": tier,
    "sell_horizon_days": days,
    "sell_horizon_label": label,
    "proxy_ticker": theme.proxy_ticker,
    "proxy_return_1m": proxy.get("return_1m"),
    "proxy_return_3m": proxy.get("return_3m"),
    "stock_trend": trend,
  }


def rank_all_picks(*, market: str | None = None, min_composite: float = 0.12) -> list[dict[str, Any]]:
  ranked: list[dict[str, Any]] = []
  for theme in THEMES:
    for stock in theme.stocks:
      if market and stock.market != market.upper():
        continue
      try:
        ev = evaluate_pick(theme, stock)
      except Exception:
        continue
      if ev["composite_score"] >= min_composite:
        ranked.append(ev)
  ranked.sort(key=lambda x: (x["composite_score"], x["expected_return_pct"]), reverse=True)
  return ranked


def build_signal_payload(pick: dict[str, Any], *, day: datetime | None = None) -> dict[str, Any]:
  now = day or datetime.now(timezone.utc)
  day_key = now.strftime("%Y-%m-%d")
  slug = pick["theme_slug"]
  ticker = pick["ticker"]
  market = pick["market"]
  composite = pick["composite_score"]
  return {
    "source": SOURCE,
    "source_ref": f"{slug}:{ticker}:{day_key}",
    "market": market,
    "entity": pick["theme_name"],
    "ticker": ticker,
    "action": "BUY",
    "qty": None,
    "value": round(composite * 1e8, 0),
    "disclosed_at": now,
    "source_url": None,
    "raw_json": {
      "theme_slug": slug,
      "theme_name": pick["theme_name"],
      "demand_driver": pick["demand_driver"],
      "world_context": pick["world_context"],
      "company_name": pick["company_name"],
      "theme_heat": pick["theme_heat"],
      "alignment_score": pick["alignment_score"],
      "composite_score": pick["composite_score"],
      "proxy_ticker": pick["proxy_ticker"],
      "proxy_return_1m": pick["proxy_return_1m"],
      "proxy_return_3m": pick["proxy_return_3m"],
    },
  }


def theme_narrative(signal_raw: dict | None) -> dict[str, Any] | None:
  if not signal_raw:
    return None
  slug = signal_raw.get("theme_slug")
  if not slug:
    return None
  heat = signal_raw.get("theme_heat")
  align = signal_raw.get("alignment_score")
  proxy = signal_raw.get("proxy_ticker")
  p1 = signal_raw.get("proxy_return_1m")
  p3 = signal_raw.get("proxy_return_3m")
  paragraphs = [
    signal_raw.get("world_context") or "",
    signal_raw.get("demand_driver") or "",
  ]
  if heat is not None:
    paragraphs.append(
      f"Theme heat score {heat * 100:.0f}/100 — sector proxy {proxy} is "
      f"{'up' if (p3 or 0) > 0 else 'down'} ~{abs((p3 or 0) * 100):.1f}% over 3 months."
    )
  if align is not None:
    paragraphs.append(
      f"Stock–theme alignment {align * 100:.0f}/100 — price action vs the theme proxy and 50-day trend."
    )
  return {
    "theme_slug": slug,
    "theme_name": signal_raw.get("theme_name"),
    "headline": f"Macro theme: {signal_raw.get('theme_name')}",
    "paragraphs": [p for p in paragraphs if p],
    "theme_heat": heat,
    "alignment_score": align,
  }
