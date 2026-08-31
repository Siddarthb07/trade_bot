"""Break-even bake-off: Lane C baseline ORB, Lane A ORB+bulk veto, Lane B copy-pro.

August ₹10k compound, capital_use=50%. Promotes only if compound>=0 and
avg PnL on trade days > 0. If bulk DB lacks Aug coverage, also scores a July
window where bulk buys exist (DATA_GAP noted for Aug A/B).
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.day_sim import simulate_day
from processor.orwidth_product import DEFAULT_PAPER_PRODUCT, product_kwargs
from processor.smart_money_gate import bulk_data_coverage

CAPITAL = 10_000.0
CAPITAL_USE = 0.50
AUG_START = "2026-08-01"
AUG_END = "2026-08-28"
# Bulk DB historically ends ~2026-07-20 — secondary window for copy-pro validity.
JULY_START = "2026-07-01"
JULY_END = "2026-07-18"


def _sessions(start: str, end: str) -> list[str]:
  sd, ed = date.fromisoformat(start), date.fromisoformat(end)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def _lane_kwargs(lane: str) -> dict:
  if lane == "C":
    kw = product_kwargs(DEFAULT_PAPER_PRODUCT)
    kw.pop("bar_interval", None)
    kw["capital_use_frac"] = CAPITAL_USE
    kw["require_bulk_confluence"] = False
    return kw
  if lane == "A":
    kw = product_kwargs(DEFAULT_PAPER_PRODUCT)
    kw.pop("bar_interval", None)
    kw["capital_use_frac"] = CAPITAL_USE
    kw["require_bulk_confluence"] = True
    kw["bulk_lookback_sessions"] = 3
    kw["bulk_min_win_rate"] = 0.55
    return kw
  if lane == "B":
    return {
      "filter_mode": "copy_bulk_pro",
      "max_leverage": 5.0,
      "conf_floor": 0.55,
      "max_daily_loss_pct": 4.0,
      "max_trade_risk_pct": 3.0,
      "intraday_stop_with_session_end": True,
      "exit_at_session_end": True,
      "max_chase_attempts": 1,
      "use_hl_exits": False,
      "max_positions": 1,
      "bulk_lookback_sessions": 1,
      "bulk_min_win_rate": 0.55,
      "capital_use_frac": CAPITAL_USE,
    }
  raise KeyError(lane)


def run_lane(lane: str, days: list[str], *, label: str) -> dict:
  kw = _lane_kwargs(lane)
  print(f"\n=== Lane {lane} | {label} | {days[0]}->{days[-1]} ({len(days)}d) ===", flush=True)
  print(f"params={kw}", flush=True)
  cap = float(CAPITAL)
  start_cap = cap
  daily: list[dict] = []
  total_trades = 0
  peak, max_dd = cap, 0.0
  min_ret, max_ret = 999.0, -999.0
  sit_outs = 0

  for i, asof in enumerate(days, 1):
    print(f"  [{i}/{len(days)}] {asof} ...", flush=True)
    res = simulate_day(
      asof=asof,
      capital=cap,
      currency="INR",
      market="IN",
      path_mode="session",
      max_positions=int(kw.get("max_positions") or 1),
      allow_demo_fallback=False,
      **{k: v for k, v in kw.items() if k != "max_positions"},
    )
    cap_start = cap
    cap_end = float(res.get("capital_end") or cap_start)
    pnl = round(cap_end - cap_start, 2)
    ret = float(res.get("return_pct") or 0)
    n_trades = int(res.get("n_trades") or 0)
    if n_trades == 0:
      sit_outs += 1
    total_trades += n_trades
    cap = cap_end
    peak = max(peak, cap)
    dd = 100.0 * (peak - cap) / peak if peak else 0.0
    max_dd = max(max_dd, dd)
    min_ret = min(min_ret, ret)
    max_ret = max(max_ret, ret)
    skip_reasons = sorted(
      {
        str(s.get("reason"))
        for s in (res.get("skipped") or [])
        if str(s.get("reason") or "").startswith("sit_out")
      }
    )
    daily.append(
      {
        "asof": asof,
        "capital_start": round(cap_start, 2),
        "capital_end": round(cap_end, 2),
        "pnl_inr": pnl,
        "return_pct": ret,
        "n_trades": n_trades,
        "sit_out": n_trades == 0,
        "skip_reasons": skip_reasons,
        "trades": [
          {
            "ticker": t.get("ticker"),
            "pnl": t.get("pnl"),
            "lev": t.get("leverage"),
            "exit": t.get("exit_reason"),
          }
          for t in (res.get("trades") or [])
        ],
      }
    )
    print(
      f"    end={cap_end:,.0f} pnl={pnl:+.1f} ret={ret:+.2f}% trades={n_trades} "
      f"sit={skip_reasons or ('-' if n_trades else 'flat')}",
      flush=True,
    )

  if min_ret > 100:
    min_ret = 0.0
  if max_ret < -100:
    max_ret = 0.0
  compound = round(100.0 * (cap - start_cap) / start_cap, 3) if start_cap else 0.0
  trade_days = [d for d in daily if d["n_trades"] > 0]
  avg_trade_day = (
    round(sum(d["pnl_inr"] for d in trade_days) / len(trade_days), 2) if trade_days else None
  )
  pass_be = compound >= 0.0 and avg_trade_day is not None and avg_trade_day > 0
  return {
    "lane": lane,
    "label": label,
    "window": {"start": days[0], "end": days[-1], "n_days": len(days)},
    "params": kw,
    "capital_start": start_cap,
    "capital_end": round(cap, 2),
    "month_pnl_inr": round(cap - start_cap, 2),
    "compound_pct": compound,
    "total_trades": total_trades,
    "sit_outs": sit_outs,
    "trade_days": len(trade_days),
    "avg_pnl_on_trade_days": avg_trade_day,
    "worst_day_pct": round(min_ret, 3),
    "best_day_pct": round(max_ret, 3),
    "max_dd_pct": round(max_dd, 3),
    "pass_break_even": pass_be,
    "daily": daily,
  }


def _append_methods_log(report: dict) -> None:
  log_path = ROOT / "docs" / "DAY_SIM_METHODS_LOG.md"
  if not log_path.exists():
    return
  tz = ZoneInfo("Asia/Kolkata")
  now = datetime.now(tz).strftime("%Y-%m-%d %H:%M IST")
  lanes = report.get("lanes") or []
  rows = []
  for r in lanes:
    rows.append(
      f"| {r['lane']} | {r['label']} | {r['compound_pct']:+.2f}% | {r['month_pnl_inr']:+.0f} | "
      f"{r['total_trades']} | {r['sit_outs']} | {r.get('avg_pnl_on_trade_days')} | "
      f"{r['max_dd_pct']:.1f}% | {r['pass_break_even']} |"
    )
  promo = report.get("promoted")
  body = f"""

## J. Break-even bake-off — ORB vs copy-pro

> Generated: {now}
> Script: `scripts/run_break_even_bakeoff.py`
> Capital INR 10,000 · capital_use=50% · Status: research / paper

### J1. Method rating (pre-bake-off)

| Rank | Method | Grade | Why |
|------|--------|-------|-----|
| 1 | Oracle session-close | Ceiling only | Move limit; not tradable |
| 2 | Raw OR-width 75x | Lottery A / keepable F | Huge compound / July wipeouts |
| 3 | Push raw tgt=5% 1-pos | Research B+ | +52% window; bad tails |
| 4 | Guarded ORB + sit-out | Product C+ | Aug ~−7% before bake-off |
| 5 | Guarded ORB pre-fix | D | Forced daily bleed |
| 6 | Hybrid product Aug MTD | D | −23.6% |
| 7 | adaptive_edge / TA stubs | Incomplete | Not month-compound wired |
| 8 | Filter / lev sweeps | F for 8–10% goal | No every-day pass |

### J2. Bake-off results

Coverage: `{json.dumps(report.get("coverage"))}`

| Lane | Window | Compound | PnL INR | Trades | Sit-outs | Avg trade-day PnL | MaxDD | Pass≥0 |
|------|--------|----------|---------|--------|----------|-------------------|-------|--------|
{chr(10).join(rows)}

**Promoted:** `{promo}`
**Reports:** `models/break_even_bakeoff.json`

### J3. Verdict

{report.get("verdict", "")}

"""
  text = log_path.read_text(encoding="utf-8")
  # Replace prior §J if present
  marker = "## J. Break-even bake-off"
  if marker in text:
    pre = text.split(marker)[0].rstrip()
    # keep changelog if after J
    after = text.split(marker, 1)[1]
    if "## Changelog" in after:
      after = "## Changelog" + after.split("## Changelog", 1)[1]
      text = pre + "\n" + body + "\n" + after
    else:
      text = pre + "\n" + body
  else:
    if "## Changelog" in text:
      text = text.replace("## Changelog", body + "\n## Changelog")
    else:
      text = text.rstrip() + "\n" + body
  # changelog row
  if "Break-even bake-off" not in text.split("## Changelog")[-1]:
    text = text.replace(
      "## Changelog\n\n| Date | Change |\n|------|--------|\n",
      "## Changelog\n\n| Date | Change |\n|------|--------|\n"
      f"| {date.today().isoformat()} | **Break-even bake-off:** lanes A/B/C; "
      f"promoted={promo}; see §J; `break_even_bakeoff.json`. |\n",
    )
  log_path.write_text(text, encoding="utf-8")


def _maybe_promote(winner: dict | None) -> str | None:
  if not winner:
    return None
  path = ROOT / "packages" / "processor" / "orwidth_product.py"
  src = path.read_text(encoding="utf-8")
  if winner["lane"] == "A":
    name = "in_tr10_orwidth_chase5_75x_guard_bulk"
    if f'DEFAULT_PAPER_PRODUCT = "{name}"' not in src:
      src = src.replace(
        'DEFAULT_PAPER_PRODUCT = "in_tr10_orwidth_chase5_75x_guard"',
        f'DEFAULT_PAPER_PRODUCT = "{name}"  # promoted {date.today().isoformat()} bake-off Lane A',
      )
      path.write_text(src, encoding="utf-8")
    return name
  if winner["lane"] == "B":
    return "copy_bulk_pro"
  if winner["lane"] == "C":
    return DEFAULT_PAPER_PRODUCT
  return None


def main() -> None:
  coverage = bulk_data_coverage(since="2026-07-01")
  print("coverage", coverage, flush=True)

  aug = _sessions(AUG_START, AUG_END)
  lanes: list[dict] = []
  for lane in ("C", "A", "B"):
    lanes.append(run_lane(lane, aug, label="august"))

  # If Aug A/B never traded due to DATA_GAP, score July window for A/B
  july = _sessions(JULY_START, JULY_END)
  need_july = any(
    r["lane"] in ("A", "B") and r["trade_days"] == 0 and r["label"] == "august" for r in lanes
  )
  if need_july and not coverage.get("data_gap"):
    print("\nAug A/B idle — running July secondary window for copy-pro validity", flush=True)
    for lane in ("A", "B"):
      lanes.append(run_lane(lane, july, label="july_bulk_window"))

  eligible = [r for r in lanes if r["pass_break_even"]]
  eligible.sort(key=lambda r: (-r["compound_pct"], r["max_dd_pct"]))
  winner = eligible[0] if eligible else None
  promoted = _maybe_promote(winner) if winner else None

  if winner:
    verdict = (
      f"PASS — Lane {winner['lane']} ({winner['label']}) compound "
      f"{winner['compound_pct']:+.2f}% with avg trade-day PnL "
      f"{winner['avg_pnl_on_trade_days']}. Promoted={promoted}."
    )
  else:
    verdict = (
      "FAIL — no lane hit compound≥0 with positive avg trade-day PnL. "
      "Product stays sit-out ORB guard; next step longer bulk OOS, not more leverage. "
      f"Coverage data_gap={coverage.get('data_gap')} window_buys={coverage.get('window_buys')}."
    )

  report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "capital": CAPITAL,
    "capital_use_frac": CAPITAL_USE,
    "coverage": coverage,
    "lanes": lanes,
    "promoted": promoted,
    "winner": {"lane": winner["lane"], "label": winner["label"]} if winner else None,
    "verdict": verdict,
    "disclaimer": "Paper/sim only — not live fills, not investment advice.",
  }
  out = ROOT / "models" / "break_even_bakeoff.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  _append_methods_log(report)
  print("\n" + verdict, flush=True)
  print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
  main()
