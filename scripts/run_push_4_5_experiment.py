"""Push experiment: 4%/5% daily targets + multi-trade OR-width hybrid grid.

Logs JSON under models/ and appends a section to docs/DAY_SIM_METHODS_LOG.md.
Research / diagnostic only — not live-eligible.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from broker.sizing import leverage_for_target
from broker.paper import PaperBroker
from processor.costs import cost_model_for
from processor.day_sim import IN_UNIVERSE_VOLATILE, simulate_day
from processor.intraday_bars import fetch_intraday_bars
from processor.orwidth_product import product_kwargs
from processor.strategies import session_or_breakout

START = 10_000.0
MAX_LEV = 75.0
# Same 12-session window as prior methods log when possible; else last 12 weekdays.
BENCH_START = "2026-08-13"
BENCH_END = "2026-08-28"
ORACLE_TARGETS = (4.0, 5.0, 8.0)
PUSH_TARGETS = (4.0, 5.0)
POSITIONS = (1, 3, 5, 8)
POLICIES = ("raw", "guard")


def _sessions(start: str, end: str) -> list[str]:
  sd, ed = date.fromisoformat(start), date.fromisoformat(end)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def _best_close_move(asof: str) -> tuple[str, float, float]:
  best = ("-", 0.0, 0.0)
  for ticker in IN_UNIVERSE_VOLATILE:
    bars = fetch_intraday_bars(ticker, session_date=asof, interval="5m", market="IN")
    if len(bars) < 12:
      continue
    sob = session_or_breakout(bars)
    if sob.get("side") != "buy":
      continue
    entry = float(sob.get("entry_px") or 0)
    if entry <= 0:
      continue
    close_px = float(bars[-1].get("close") or entry)
    move = 100.0 * (close_px / entry - 1.0)
    or_w = float(sob.get("or_width_pct") or 0)
    if move > best[1]:
      best = (ticker, move, or_w)
  return best


def _oracle_day(asof: str, capital: float, target_pct: float) -> dict:
  ticker, move_pct, or_w = _best_close_move(asof)
  if ticker == "-" or move_pct <= 0:
    return {
      "asof": asof,
      "return_pct": 0.0,
      "capital_end": capital,
      "ticker": None,
      "move_pct": 0.0,
      "unreachable_at_4": True,
      "unreachable_at_5": True,
    }
  cm = cost_model_for("IN")
  broker = PaperBroker("IN", starting_cash=capital, currency="INR", leverage_max=MAX_LEV)
  exp = max(or_w, abs(move_pct) / 100.0, 0.004)
  lev = leverage_for_target(target_pct / 100.0, exp, max_leverage=MAX_LEV)
  notional = min(capital * lev, broker.buying_power() * 0.98)
  fee = cm.fee_on_notional(notional, sides=2)
  pnl = notional * (move_pct / 100.0) - fee
  cap_end = max(broker.cash + pnl - broker.borrowed, 0.0)
  ret = 100.0 * (cap_end - capital) / capital if capital else 0.0
  return {
    "asof": asof,
    "return_pct": round(ret, 3),
    "capital_end": round(cap_end, 2),
    "ticker": ticker,
    "move_pct": round(move_pct, 3),
    "lev": round(lev, 2),
    "target_pct": target_pct,
    "unreachable_at_4": move_pct < 0.08,  # rough: tiny tape can't print 4% after costs@lev
    "unreachable_at_5": move_pct < 0.10,
  }


def run_oracle(days: list[str]) -> dict:
  report: dict = {"sessions": days, "targets": {}, "generated_at": datetime.now(timezone.utc).isoformat()}
  print(f"\n=== ORACLE 4/5/8% (perfect pick, session-close, costs) | {days[0]} -> {days[-1]} ===", flush=True)
  for tgt in ORACLE_TARGETS:
    cap = START
    rows = []
    for asof in days:
      print(f"  oracle tgt={tgt} {asof} ...", flush=True)
      row = _oracle_day(asof, cap, tgt)
      cap = float(row["capital_end"])
      rows.append(row)
    rets = [r["return_pct"] for r in rows]
    ge4 = sum(1 for r in rets if r >= 4.0)
    ge5 = sum(1 for r in rets if r >= 5.0)
    ge8 = sum(1 for r in rets if r >= 8.0)
    report["targets"][str(tgt)] = {
      "min_daily_return_pct": min(rets) if rets else 0,
      "max_daily_return_pct": max(rets) if rets else 0,
      "avg_daily_return_pct": round(sum(rets) / len(rets), 3) if rets else 0,
      "days_ge_4": ge4,
      "days_ge_5": ge5,
      "days_ge_8": ge8,
      "hit_at_4_pct": round(100.0 * ge4 / len(days), 1) if days else 0,
      "hit_at_5_pct": round(100.0 * ge5 / len(days), 1) if days else 0,
      "all_ge_4": ge4 == len(days),
      "all_ge_5": ge5 == len(days),
      "compound_pct": round(100.0 * (cap - START) / START, 2),
      "days": rows,
    }
    t = report["targets"][str(tgt)]
    print(
      f"  Target {tgt}%: min={t['min_daily_return_pct']:.2f}% compound={t['compound_pct']:.1f}% "
      f"hit@4={t['days_ge_4']}/{len(days)} hit@5={t['days_ge_5']}/{len(days)} "
      f"ALL>=4={t['all_ge_4']} ALL>=5={t['all_ge_5']}",
      flush=True,
    )
  return report


def _compound_window(days: list[str], *, target: float, positions: int, policy: str) -> dict:
  base_name = "in_tr10_orwidth_chase5_75x_guard" if policy == "guard" else "in_tr10_orwidth_chase5_75x"
  kw = product_kwargs(base_name)
  kw["target_return_pct"] = float(target)
  # positions==1: classic chase; positions>1: parallel slots (equal capital split)
  kw["max_chase_attempts"] = 5 if int(positions) <= 1 else 1
  kw.pop("bar_interval", None)
  cap = START
  daily = []
  peak = cap
  max_dd = 0.0
  total_trades = 0
  for asof in days:
    print(f"  push {policy} tgt={target} pos={positions} {asof} ...", flush=True)
    sim = simulate_day(
      asof=asof,
      capital=cap,
      currency="INR",
      market="IN",
      path_mode="session",
      max_positions=positions,
      allow_demo_fallback=False,
      **kw,
    )
    ret = float(sim.get("return_pct") or 0)
    cap = float(sim.get("capital_end") or cap)
    n_tr = int(sim.get("n_trades") or 0)
    total_trades += n_tr
    peak = max(peak, cap)
    dd = 100.0 * (peak - cap) / peak if peak else 0.0
    max_dd = max(max_dd, dd)
    daily.append(
      {
        "asof": asof,
        "return_pct": ret,
        "capital_end": round(cap, 2),
        "n_trades": n_tr,
        "realized_pnl": sim.get("realized_pnl"),
      }
    )
  rets = [d["return_pct"] for d in daily]
  ge4 = sum(1 for r in rets if r >= 4.0)
  ge5 = sum(1 for r in rets if r >= 5.0)
  return {
    "policy": policy,
    "target_return_pct": target,
    "max_positions": positions,
    "n_days": len(days),
    "capital_start": START,
    "capital_end": round(cap, 2),
    "compound_pct": round(100.0 * (cap - START) / START, 3),
    "min_day_pct": round(min(rets), 3) if rets else 0,
    "max_day_pct": round(max(rets), 3) if rets else 0,
    "avg_day_pct": round(sum(rets) / len(rets), 3) if rets else 0,
    "days_ge_4": ge4,
    "days_ge_5": ge5,
    "hit_at_4_pct": round(100.0 * ge4 / len(days), 1) if days else 0,
    "hit_at_5_pct": round(100.0 * ge5 / len(days), 1) if days else 0,
    "max_dd_pct": round(max_dd, 3),
    "total_trades": total_trades,
    "trades_per_day": round(total_trades / len(days), 2) if days else 0,
    "daily": daily,
  }


def run_push_grid(days: list[str]) -> list[dict]:
  rows = []
  print(f"\n=== PUSH GRID multi-trade OR-width | {days[0]} -> {days[-1]} ===", flush=True)
  for policy in POLICIES:
    for tgt in PUSH_TARGETS:
      for pos in POSITIONS:
        row = _compound_window(days, target=tgt, positions=pos, policy=policy)
        rows.append(row)
        print(
          f"  {policy:5s} tgt={tgt} pos={pos} compound={row['compound_pct']:+.2f}% "
          f"hit@4={row['days_ge_4']}/{row['n_days']} hit@5={row['days_ge_5']}/{row['n_days']} "
          f"min={row['min_day_pct']:+.2f}% trades/day={row['trades_per_day']} DD={row['max_dd_pct']:.1f}%",
          flush=True,
        )
  return rows


def _md_section(oracle: dict, push: list[dict], days: list[str]) -> str:
  now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M %Z")
  lines = [
    "",
    "---",
    "",
    "## I. Push experiment — 4%/5% daily + multi-trade hybrid",
    "",
    f"> Generated: {now}  ",
    f"> Script: `scripts/run_push_4_5_experiment.py`  ",
    f"> Window: **{days[0]} -> {days[-1]}** ({len(days)} sessions) · Capital INR {START:,.0f}  ",
    "> Status: **VALIDATED / research** — not live-eligible. Goal = maximize hit@4 / hit@5 + compound; not every-day floor.",
    "",
    "### I1. Oracle ceiling at 4% / 5% / 8% (perfect ticker, session-close, costs, 75x)",
    "",
    "| Target | Min/day% | Avg/day% | Max/day% | Compound% | Hit@4 | Hit@5 | Hit@8 | ALL>=4 | ALL>=5 |",
    "|--------|----------|----------|----------|-----------|-------|-------|-------|--------|--------|",
  ]
  for tgt in ORACLE_TARGETS:
    t = oracle["targets"][str(tgt)]
    n = len(days)
    lines.append(
      f"| {tgt:g}% | {t['min_daily_return_pct']:.2f} | {t['avg_daily_return_pct']:.2f} | "
      f"{t['max_daily_return_pct']:.2f} | {t['compound_pct']:.1f} | "
      f"{t['days_ge_4']}/{n} | {t['days_ge_5']}/{n} | {t['days_ge_8']}/{n} | "
      f"{t['all_ge_4']} | {t['all_ge_5']} |"
    )
  lines.extend(
    [
      "",
      "**Per-day oracle (target 4% sizing)** — move = best ORB→session-close %:",
      "",
      "| Day | Ticker | Move% | Ret% | >=4? | >=5? |",
      "|-----|--------|-------|------|------|------|",
    ]
  )
  for r in oracle["targets"]["4.0"]["days"]:
    lines.append(
      f"| {r['asof']} | {r.get('ticker') or '-'} | {r.get('move_pct', 0):.3f} | "
      f"{r['return_pct']:+.2f} | {'Y' if r['return_pct'] >= 4 else 'N'} | "
      f"{'Y' if r['return_pct'] >= 5 else 'N'} |"
    )
  unreachable = [r["asof"] for r in oracle["targets"]["4.0"]["days"] if r["return_pct"] < 4.0]
  lines.extend(
    [
      "",
      f"**Oracle-unreachable at 4% (this window):** {', '.join(unreachable) if unreachable else '(none)'}",
      "",
      "### I2. Multi-trade OR-width push grid",
      "",
      "Policies: `raw` = `in_tr10_orwidth_chase5_75x`; `guard` = guarded product. "
      "`max_positions` raised (day_sim no longer forces 1 in target_return). "
      "`max_chase_attempts = max(5, positions)`. Target return sizing 4% or 5%.",
      "",
      "| Policy | Target% | Positions | Compound% | Hit@4 | Hit@5 | Min/day% | Max/day% | Trades/day | MaxDD% |",
      "|--------|---------|-----------|-----------|-------|-------|----------|----------|------------|--------|",
    ]
  )
  ranked = sorted(push, key=lambda r: (-r["hit_at_4_pct"], -r["compound_pct"]))
  for r in ranked:
    lines.append(
      f"| {r['policy']} | {r['target_return_pct']:g} | {r['max_positions']} | "
      f"{r['compound_pct']:+.2f} | {r['days_ge_4']}/{r['n_days']} | {r['days_ge_5']}/{r['n_days']} | "
      f"{r['min_day_pct']:+.2f} | {r['max_day_pct']:+.2f} | {r['trades_per_day']:.2f} | {r['max_dd_pct']:.1f} |"
    )
  best = ranked[0] if ranked else None
  lines.extend(["", "### I3. Verdict", ""])
  if best:
    lines.append(
      f"- **Best by hit@4 then compound:** `{best['policy']}` target={best['target_return_pct']}% "
      f"positions={best['max_positions']} → hit@4={best['days_ge_4']}/{best['n_days']} "
      f"({best['hit_at_4_pct']}%), compound={best['compound_pct']:+.2f}%, "
      f"min/day={best['min_day_pct']:+.2f}%, trades/day={best['trades_per_day']}."
    )
  o4 = oracle["targets"]["4.0"]
  lines.extend(
    [
      f"- **Oracle at 4% target sizing:** hit@4={o4['days_ge_4']}/{len(days)}, "
      f"ALL>=4={o4['all_ge_4']}, compound={o4['compound_pct']:.1f}%, min/day={o4['min_daily_return_pct']:.2f}%.",
      "- **Takeaway:** Raising trade count cannot beat the oracle move ceiling on dead sessions. "
      "Promote to product only if a guard config beats prior `primary_score` without worse tails; "
      "otherwise keep as research ceiling map.",
      "- Reports: `models/oracle_4_5_ceiling.json`, `models/push_4_5_experiment.json`.",
      "",
    ]
  )
  return "\n".join(lines)


def _patch_goal_status(md: str, oracle: dict, days: list[str]) -> str:
  """Update goal status table rows for 4/5 experiment without rewriting whole file."""
  o4 = oracle["targets"]["4.0"]
  o5 = oracle["targets"]["5.0"]
  n = len(days)
  extra = (
    f"| Goal met (4% every day, oracle) | **{'YES' if o4['all_ge_4'] else 'NO'}** — "
    f"oracle hit@4={o4['days_ge_4']}/{n}; see §I |\n"
    f"| Goal met (5% every day, oracle) | **{'YES' if o5['all_ge_5'] else 'NO'}** — "
    f"oracle hit@5={o5['days_ge_5']}/{n}; see §I |"
  )
  marker = "| Live eligibility | **None** — sim research only |"
  if "Goal met (4% every day, oracle)" in md:
    return md
  return md.replace(marker, extra + "\n" + marker)


def _append_changelog(md: str) -> str:
  row = (
    "| 2026-08-29 | **Push 4%/5% + multi-trade:** oracle ceiling + OR-width position grid; "
    "logged §I; JSON `oracle_4_5_ceiling.json` / `push_4_5_experiment.json`. |"
  )
  if "Push 4%/5% + multi-trade" in md:
    return md
  if md.rstrip().endswith("|"):
    return md.rstrip() + "\n" + row + "\n"
  # find changelog table end
  if "## Changelog" in md:
    return md.rstrip() + "\n" + row + "\n"
  return md


def main() -> None:
  days = _sessions(BENCH_START, BENCH_END)
  if len(days) < 5:
    ist = ZoneInfo("Asia/Kolkata")
    end = datetime.now(ist).date()
    while end.weekday() >= 5:
      end -= timedelta(days=1)
    days = []
    d = end
    while len(days) < 12:
      if d.weekday() < 5:
        days.append(d.isoformat())
      d -= timedelta(days=1)
    days = list(reversed(days))

  oracle = run_oracle(days)
  (ROOT / "models" / "oracle_4_5_ceiling.json").write_text(json.dumps(oracle, indent=2), encoding="utf-8")

  push = run_push_grid(days)
  push_report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "sessions": days,
    "capital": START,
    "runs": push,
  }
  (ROOT / "models" / "push_4_5_experiment.json").write_text(json.dumps(push_report, indent=2), encoding="utf-8")

  md_path = ROOT / "docs" / "DAY_SIM_METHODS_LOG.md"
  md = md_path.read_text(encoding="utf-8")
  section = _md_section(oracle, push, days)
  if "## I. Push experiment" in md:
    # replace from ## I. to end of file before changelog, or append replace
    pre, _, rest = md.partition("## I. Push experiment")
    # keep changelog if after section
    if "## Changelog" in rest:
      _, _, clog = rest.partition("## Changelog")
      md = pre.rstrip() + "\n" + section + "\n## Changelog" + clog
    else:
      md = pre.rstrip() + "\n" + section
  else:
    if "## Changelog" in md:
      pre, _, clog = md.partition("## Changelog")
      md = pre.rstrip() + "\n" + section + "\n## Changelog" + clog
    else:
      md = md.rstrip() + "\n" + section

  md = _patch_goal_status(md, oracle, days)
  md = _append_changelog(md)
  md_path.write_text(md, encoding="utf-8")
  print(f"\nWrote models/oracle_4_5_ceiling.json, models/push_4_5_experiment.json", flush=True)
  print(f"Appended section I -> {md_path}", flush=True)


if __name__ == "__main__":
  main()
