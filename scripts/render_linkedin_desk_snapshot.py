"""Render a LinkedIn crop from real Pattern Lab CSS + Pattern Forge artifacts.

Not an AI mock: HTML clones the dashboard chrome, data is from v2_latest /
decisions / trades. Playwright screenshots at LinkedIn 16:9.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "apps" / "dashboard" / "src" / "styles.css"
V2_PATH = ROOT / "models" / "pattern_forge" / "v2_latest.json"
DECISIONS = ROOT / "models" / "pattern_forge" / "decisions.jsonl"
TRADES = ROOT / "models" / "pattern_forge" / "trades.jsonl"
OUT_HTML = ROOT / "models" / "pattern_forge" / "plots" / "linkedin_desk_snapshot.html"
OUT_PNG = ROOT / "models" / "pattern_forge" / "plots" / "linkedin_godfather_desk_real.png"

MONTH_MAP = {
  "january": "Jan",
  "february": "Feb",
  "march": "Mar",
  "april": "Apr",
  "may": "May",
  "june": "Jun",
  "july": "Jul",
  "august": "Aug",
  "september": "Sep",
  "october": "Oct",
  "november": "Nov",
  "december": "Dec",
}


def _extract_css() -> str:
  raw = CSS_PATH.read_text(encoding="utf-8")
  # Keep root/app chrome + full pattern-lab block through end of file (pl-* lives there).
  start = raw.find(".pattern-lab {")
  if start < 0:
    raise SystemExit("pattern-lab CSS missing")
  # Also grab :root through .footer basics for authentic chrome
  head = raw[: raw.find("/* Cards */")] if "/* Cards */" in raw else raw[:900]
  # Prefer first ~900 chars which include :root, body, header, main, footer
  head = "\n".join(raw.splitlines()[:70])
  return head + "\n" + raw[start:]


def _load_decisions(limit: int = 16) -> list[dict]:
  rows: list[dict] = []
  with DECISIONS.open(encoding="utf-8") as f:
    for line in f:
      d = json.loads(line)
      msgs = d.get("swarm_messages") or []
      if len(msgs) < 6:
        continue
      rows.append(d)
      if len(rows) >= 80:
        break
  # Prefer tradeable fires near the end of the collected set
  fires = [d for d in rows if (d.get("swarm_agreement") or {}).get("tradeable")]
  picks = (fires[-limit:] if fires else rows[-limit:])
  return list(reversed(picks))


def _load_trades(limit: int = 18) -> list[dict]:
  if not TRADES.exists():
    return []
  rows: list[dict] = []
  with TRADES.open(encoding="utf-8") as f:
    for line in f:
      rows.append(json.loads(line))
  return list(reversed(rows[-limit:]))


def _fmt_pct(n: float | None) -> str:
  if n is None:
    return "—"
  return f"{n:+.2f}%"


def _fmt_inr(n: float | None) -> str:
  if n is None:
    return "—"
  return f"₹{n:,.0f}"


def _month_chips(months: list[dict]) -> str:
  bits = []
  for m in months:
    lab = MONTH_MAP.get(str(m.get("month", "")).lower(), str(m.get("month", ""))[:3])
    ret = float(m.get("month_return_pct") or 0)
    cls = "up" if ret >= 0 else "down"
    n = int(m.get("n_trades") or 0)
    bits.append(
      f'<div class="pl-month {cls}"><span>{lab}</span>'
      f"<strong class=\"{cls}\">{_fmt_pct(ret)}</strong>"
      f"<em>{n} tr · {_fmt_inr(m.get('capital_end'))}</em></div>"
    )
  return "".join(bits)


def _agent_cards(msgs: list[dict]) -> str:
  bits = []
  for m in msgs:
    vote = m.get("vote") or "annotate"
    agent = m.get("agent") or "?"
    reason = m.get("reason") or ""
    stub = m.get("status") in {"insufficient_data", "missing", "cold_start"} or agent in {
      "VPIN",
      "Hawkes",
      "Kyle",
    }
    stub_cls = " stub" if stub else ""
    stub_tag = '<span class="pl-stub-tag">stub</span>' if stub else ""
    bits.append(
      f'<article class="pl-agent-card{stub_cls}"><header>'
      f"<h3>{agent}</h3>"
      f'<span class="pl-vote-pill {vote}">{vote}</span>{stub_tag}'
      f"</header><p class=\"muted\" style=\"margin:0;font-size:0.72rem;line-height:1.35\">{reason}</p>"
      f"</article>"
    )
  return "".join(bits)


def _tape(decisions: list[dict]) -> str:
  bits = []
  for i, d in enumerate(decisions):
    choice = str(d.get("choice") or "skip")
    fire = "fire" if choice == "fire" else ("no_ruin" if "ruin" in choice else "skip")
    tkr = str(d.get("ticker") or "—").replace(".NS", "")
    asof = str(d.get("asof") or "")[:10]
    fam = str(d.get("family") or "")
    agr = d.get("swarm_agreement") or {}
    score = agr.get("score")
    score_s = f"score {float(score):.2f}" if score is not None else ""
    active = " active" if i == 0 else ""
    bits.append(
      f'<button type="button" class="pl-tape-row{active}">'
      f'<span class="pl-choice {fire}">{fire}</span>'
      f'<div class="pl-tape-main"><strong>{tkr}</strong><em>{fam}</em></div>'
      f'<div class="pl-tape-meta">{asof} · {score_s}</div></button>'
    )
  return "".join(bits)


def _equity_svg(months: list[dict]) -> str:
  caps = [float(months[0]["capital_start"])] + [float(m["capital_end"]) for m in months]
  w, h = 520, 118
  pad = 6
  mn, mx = min(caps), max(caps)
  span = max(mx - mn, 1.0)
  pts = []
  for i, c in enumerate(caps):
    x = pad + (w - 2 * pad) * i / (len(caps) - 1)
    y = pad + (h - 2 * pad) * (1 - (c - mn) / span)
    pts.append(f"{x:.1f},{y:.1f}")
  poly = " ".join(pts)
  # area fill under line
  area = f"{pad},{h - pad} " + poly + f" {w - pad},{h - pad}"
  return (
    f'<svg viewBox="0 0 {w} {h}" width="100%" height="118" preserveAspectRatio="none" aria-hidden="true">'
    f'<polyline fill="rgba(48,209,88,0.12)" stroke="none" points="{area}"/>'
    f'<polyline fill="none" stroke="#30d158" stroke-width="2" points="{poly}"/>'
    f"</svg>"
  )


def build_html() -> str:
  v2 = json.loads(V2_PATH.read_text(encoding="utf-8"))
  months = v2["months"]
  decisions = _load_decisions(14)
  selected = decisions[0] if decisions else {}
  msgs = selected.get("swarm_messages") or []
  trades = _load_trades(12)
  css = _extract_css()

  take_n = sum(1 for m in msgs if m.get("vote") == "take")
  skip_n = sum(1 for m in msgs if m.get("vote") == "skip")
  ann_n = len(msgs) - take_n - skip_n
  agr = selected.get("swarm_agreement") or {}

  trade_rows = []
  for t in trades:
    pnl = float(t.get("pnl") or 0)
    cls = "up" if pnl >= 0 else "down"
    trade_rows.append(
      f"<li><span class=\"pl-list-title\">{str(t.get('ticker','')).replace('.NS','')}</span>"
      f"<span class=\"muted\">{str(t.get('asof') or t.get('ts') or '')[:10]}</span>"
      f"<span class=\"{cls}\">{_fmt_inr(pnl)}</span></li>"
    )

  html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>GodFather · Pattern Lab</title>
<style>
{css}
.main {{ max-width: 1180px; }}
.pl-shot {{
  /* LinkedIn 16:9 crop frame */
  width: 1280px;
  height: 720px;
  overflow: hidden;
  position: relative;
}}
.pl-shot .pattern-lab {{ max-width: none; padding-bottom: 0; }}
.pl-dense-meta {{
  font-size: 0.62rem;
  color: var(--pl-muted);
  letter-spacing: 0.02em;
  line-height: 1.35;
  margin: 0.35rem 0 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.pl-agent-cards {{ max-height: 210px; }}
.pl-tape {{ max-height: 210px; }}
.pl-grid-shot {{
  display: grid;
  grid-template-columns: 0.95fr 1.25fr;
  gap: 0.85rem;
}}
.pl-panel {{ margin-bottom: 0.75rem; }}
.pl-metrics {{ margin-bottom: 0.75rem; padding: 0.85rem 1rem; }}
header.header {{ padding: 0.55rem 1rem; }}
.main {{ padding: 0.65rem 1rem 0.5rem; }}
footer.footer {{ display: none; }}
.pl-mini-claim {{
  font-size: 0.58rem;
  color: rgba(242,243,245,0.38);
  margin-top: 0.45rem;
}}
</style>
</head>
<body>
<div class="app pl-shot" id="shot">
  <header class="header">
    <div class="header-brand">
      <strong>GodFather</strong>
      <span class="subtitle">Not investment advice</span>
    </div>
    <nav class="header-nav">
      <a href="#">Demand picks</a>
      <a href="#">Bulk deals</a>
      <a href="#">Portfolio</a>
      <a href="#">Live</a>
      <a href="#">GodFather</a>
      <a href="#" class="active">Pattern Lab</a>
      <a href="#">Investors</a>
    </nav>
  </header>
  <main class="main">
    <div class="pattern-lab">
      <header class="pl-hero">
        <div class="pl-hero-copy">
          <p class="pl-eyebrow">Pattern Lab</p>
          <h1>Forge desk</h1>
          <p class="pl-sub">
            Locked hero <span class="pl-badge">v2</span>
            · clean-PIT daily swing · paper/sim only
          </p>
        </div>
        <div class="pl-hero-actions">
          <button type="button" class="pl-btn">Refresh</button>
        </div>
      </header>

      <nav class="pl-tabs" aria-label="Pattern Lab sections">
        <button type="button" class="pl-tab active">Overview</button>
        <button type="button" class="pl-tab">Swarm</button>
        <button type="button" class="pl-tab">Ledger</button>
      </nav>

      <section class="pl-glass pl-metrics" aria-label="Hero metrics">
        <div class="pl-metric">
          <span class="pl-metric-label">End capital</span>
          <strong class="up">{_fmt_inr(v2.get('capital_end'))}</strong>
          <span class="pl-soft">from {_fmt_inr(v2.get('capital_start'))}</span>
        </div>
        <div class="pl-metric">
          <span class="pl-metric-label">Year return</span>
          <strong class="up">{_fmt_pct(float(v2.get('total_return_pct') or 0))}</strong>
          <span class="pl-soft">{_fmt_inr(v2.get('year_pnl'))} pnl</span>
        </div>
        <div class="pl-metric">
          <span class="pl-metric-label">Worst month</span>
          <strong class="up">{_fmt_pct(float(v2.get('worst_month_pct') or 0))}</strong>
          <span class="pl-soft">{_fmt_inr(v2.get('worst_month_pnl'))}</span>
        </div>
        <div class="pl-metric">
          <span class="pl-metric-label">Loss ≤ profits</span>
          <strong class="up">{"Yes" if v2.get("loss_lte_profits") else "No"}</strong>
          <span class="pl-soft">{v2.get("green_months")}/{v2.get("months_total")} green · {v2.get("n_trades")} trades</span>
        </div>
      </section>

      <div class="pl-grid-shot">
        <section class="pl-glass pl-panel">
          <div class="pl-panel-head">
            <h2>2025 equity path</h2>
            <p class="pl-soft">run {v2.get("run_id")} · lev {v2.get("knobs", {}).get("leverage")}×</p>
          </div>
          {_equity_svg(months)}
          <div class="pl-month-strip" style="margin-top:0.55rem">{_month_chips(months)}</div>
          <p class="pl-mini-claim">{v2.get("claim")}</p>
        </section>

        <section class="pl-glass pl-panel pl-inspector">
          <div class="pl-panel-head pl-inspector-head">
            <div>
              <h2>Swarm · {str(selected.get("ticker") or "").replace(".NS", "")}</h2>
              <p class="muted" style="font-size:0.78rem">{str(selected.get("asof") or "")[:10]} · {selected.get("family")} · choice {selected.get("choice")}</p>
            </div>
            <div class="pl-scoreboard">
              <span class="pl-score take">take {take_n}</span>
              <span class="pl-score skip">skip {skip_n}</span>
              <span class="pl-score annotate">· {ann_n}</span>
              <span class="pl-score">τ {agr.get("tau", "—")} · {float(agr.get("score") or 0):.2f}</span>
            </div>
          </div>
          <div class="pl-grid" style="grid-template-columns: 0.85fr 1.15fr; margin-bottom:0;">
            <ul class="pl-tape">{_tape(decisions)}</ul>
            <div class="pl-agent-cards">{_agent_cards(msgs)}</div>
          </div>
          <p class="pl-dense-meta">
            agents={len(msgs)} · tradeable={agr.get("tradeable")} · collapsed={agr.get("collapsed_votes")} ·
            primary={((selected.get("primary") or {}).get("reason"))} · knobs profit_guard={v2.get("profit_guard")} sleeve={v2.get("knobs", {}).get("sleeve_frac")}
          </p>
        </section>
      </div>
    </div>
  </main>
</div>
</body>
</html>
"""
  return html


def screenshot(html_path: Path, png_path: Path) -> None:
  from playwright.sync_api import sync_playwright

  uri = html_path.resolve().as_uri()
  with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
    page.goto(uri, wait_until="networkidle")
    page.locator("#shot").screenshot(path=str(png_path), type="png")
    browser.close()


def main() -> None:
  OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
  OUT_HTML.write_text(build_html(), encoding="utf-8")
  screenshot(OUT_HTML, OUT_PNG)
  print(OUT_PNG)


if __name__ == "__main__":
  main()
