"""Stress-test OR-width chase5 hero configs across 15-day windows.

Supports:
- Resume via checkpoint (--resume)
- Prefetch pass (--prefetch)
- Historical NIFTY crash windows on 1h bars (--historical-bad)
- Leverage push grid on hero configs (--leverage-push)
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import run_in_compound_search as compound

HERO_BASE = {
  "filter_mode": "target_return",
  "conf_floor": 0.48,
  "min_or_pct": 0.0015,
  "exit_at_session_end": True,
  "rank_by": "or_width",
  "max_chase_attempts": 5,
  "bar_interval": "auto",
}

HERO_CONFIGS: list[dict] = [
  {"name": "in_tr10_orwidth_chase5_75x", "target_return_pct": 10.0, "max_leverage": 75.0, **HERO_BASE},
  {"name": "in_tr8_orwidth_chase5_75x", "target_return_pct": 8.0, "max_leverage": 75.0, **HERO_BASE},
]

LEVERAGE_PUSH = [50.0, 75.0, 100.0, 125.0, 150.0]

INTRADAY_FLOOR_5M = None  # computed dynamically in main()
REPORT_PATH = ROOT / "models" / "orwidth_stress_report.json"
CHECKPOINT_PATH = ROOT / "models" / "orwidth_stress_checkpoint.json"
LOG_START = "<!-- AUTO:ORWIDTH_STRESS_START -->"
LOG_END = "<!-- AUTO:ORWIDTH_STRESS_END -->"


def _trading_days_between(start: date, end: date) -> list[str]:
  out: list[str] = []
  d = start
  while d <= end:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def _window_ending(all_days: list[str], end_iso: str, n: int) -> list[str] | None:
  if end_iso not in all_days:
    return None
  i = all_days.index(end_iso)
  if i < n - 1:
    return None
  return all_days[i - n + 1 : i + 1]


def _nifty_15d_windows(start: date, end: date, n_sessions: int, *, floor: date | None = None) -> list[dict]:
  hist = yf.Ticker("^NSEI").history(
    start=(start - timedelta(days=40)).isoformat(),
    end=(end + timedelta(days=1)).isoformat(),
    interval="1d",
    auto_adjust=True,
  )
  if hist is None or hist.empty:
    return []
  hist = hist.sort_index()
  idx = list(hist.index)
  rows: list[dict] = []
  for i in range(n_sessions - 1, len(hist)):
    sd_ts, ed_ts = idx[i - n_sessions + 1], idx[i]
    sd = sd_ts.date() if hasattr(sd_ts, "date") else sd_ts.to_pydatetime().date()
    ed = ed_ts.date() if hasattr(ed_ts, "date") else ed_ts.to_pydatetime().date()
    if sd < start or ed > end:
      continue
    if floor and sd < floor:
      pass  # still include for historical_bad with 1h bars
    c0, c1 = float(hist["Close"].iloc[i - n_sessions + 1]), float(hist["Close"].iloc[i])
    ret = 100.0 * (c1 / c0 - 1.0) if c0 else 0.0
    rows.append({"start": sd.isoformat(), "end": ed.isoformat(), "nifty_return_pct": round(ret, 3)})
  return rows


def _sessions_for_window(start_iso: str, end_iso: str) -> list[str]:
  sd = datetime.fromisoformat(start_iso).date()
  ed = datetime.fromisoformat(end_iso).date()
  return _trading_days_between(sd, ed)


def _pick_windows(
  *,
  floor_5m: date,
  end: date,
  n_sessions: int,
  n_bad: int,
  n_good: int,
  n_random: int,
  n_historical_bad: int,
  seed: int,
) -> list[dict]:
  all_days_5m = _trading_days_between(floor_5m, end)
  nifty_recent = _nifty_15d_windows(floor_5m, end, n_sessions)
  nifty_recent.sort(key=lambda x: x["nifty_return_pct"])

  chosen: list[dict] = []
  used: set[tuple[str, str]] = set()

  def add(w: dict, label: str, wid: str, *, bar_interval: str = "auto") -> None:
    key = (w["start"], w["end"])
    if key in used:
      return
    used.add(key)
    sessions = _sessions_for_window(w["start"], w["end"])
    if len(sessions) < n_sessions:
      days = _window_ending(
        _trading_days_between(datetime.fromisoformat(w["start"]).date(), datetime.fromisoformat(w["end"]).date()),
        w["end"],
        n_sessions,
      )
      sessions = days or sessions
    if len(sessions) < max(3, n_sessions // 2):
      return
    chosen.append(
      {
        "id": wid,
        "label": label,
        "start": w["start"],
        "end": w["end"],
        "nifty_return_pct": w.get("nifty_return_pct"),
        "bar_interval": bar_interval,
        "sessions": sessions[-n_sessions:] if len(sessions) >= n_sessions else sessions,
      }
    )

  for i, w in enumerate(nifty_recent[:n_bad]):
    add(w, "bad_market", f"bad_nifty_{i + 1}", bar_interval="auto")

  for i, w in enumerate(reversed(nifty_recent[-n_good:]) if n_good else []):
    add(w, "good_market", f"good_nifty_{i + 1}", bar_interval="auto")

  if all_days_5m:
    bench_end = all_days_5m[-1]
    bench = _window_ending(all_days_5m, bench_end, n_sessions)
    if bench:
      nw = next((x for x in nifty_recent if x["end"] == bench_end), None)
      add(
        {"start": bench[0], "end": bench[-1], "nifty_return_pct": nw["nifty_return_pct"] if nw else None},
        "benchmark",
        "benchmark_latest",
        bar_interval="auto",
      )

  # Historical crash windows (Mar 2026 etc.) — 1h bars
  hist_start = date(2025, 8, 1)
  nifty_hist = _nifty_15d_windows(hist_start, end, n_sessions)
  nifty_hist.sort(key=lambda x: x["nifty_return_pct"])
  for i, w in enumerate(nifty_hist[:n_historical_bad]):
    if w["end"] >= floor_5m.isoformat() and w in nifty_recent[:n_bad]:
      continue
    add(w, "historical_bad", f"hist_bad_{i + 1}", bar_interval="1h")

  candidates = [w for w in nifty_recent if (w["start"], w["end"]) not in used]
  rng = random.Random(seed)
  rng.shuffle(candidates)
  ri = 0
  for w in candidates:
    if len([c for c in chosen if c["label"] == "random"]) >= n_random:
      break
    add(w, "random", f"random_{ri + 1}", bar_interval="auto")
    ri += 1

  return chosen


def _configs_for_run(leverage_push: bool) -> list[dict]:
  if not leverage_push:
    return HERO_CONFIGS
  out: list[dict] = []
  for lev in LEVERAGE_PUSH:
    for base in HERO_CONFIGS:
      name = base["name"].replace("_75x", f"_{int(lev)}x")
      out.append({**base, "name": name, "max_leverage": lev})
  return out


def _summarize_config(windows: list[dict], name: str) -> dict:
  rows = [w["results"][name] for w in windows if name in w.get("results", {})]
  if not rows:
    return {}
  profitable = sum(1 for r in rows if r.get("compound_total_pct", 0) > 0)

  def _avg(label: str) -> float:
    xs = [
      w["results"][name]["compound_total_pct"]
      for w in windows
      if w.get("label") == label and name in w.get("results", {})
    ]
    return round(sum(xs) / len(xs), 2) if xs else 0.0

  return {
    "windows": len(rows),
    "windows_profitable": profitable,
    "pct_profitable": round(100.0 * profitable / len(rows), 1),
    "avg_compound_pct": round(sum(r["compound_total_pct"] for r in rows) / len(rows), 2),
    "worst_compound_pct": min(r["compound_total_pct"] for r in rows),
    "best_compound_pct": max(r["compound_total_pct"] for r in rows),
    "worst_min_day_pct": min(r["min_daily_return_pct"] for r in rows),
    "bad_market_avg_compound": _avg("bad_market"),
    "historical_bad_avg_compound": _avg("historical_bad"),
  }


def _save_checkpoint(report: dict) -> None:
  CHECKPOINT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _patch_log(report: dict) -> None:
  log_path = ROOT / "docs" / "DAY_SIM_METHODS_LOG.md"
  if not log_path.exists():
    return
  text = log_path.read_text(encoding="utf-8")
  lines = [
    f"Generated: {report.get('generated_at')}",
    "",
    f"**Window:** {report.get('window_sessions')} sessions | **5m floor:** {report.get('intraday_floor_5m')}",
    f"**Windows:** {len(report.get('windows') or [])} | **Historical bad (1h):** "
    f"{sum(1 for w in report.get('windows') or [] if w.get('label')=='historical_bad')}",
    "",
    "| Config | Win% | Avg compound | Worst compound | Hist-bad avg | Worst min-day |",
    "|--------|------|--------------|----------------|--------------|---------------|",
  ]
  for name, s in (report.get("summary") or {}).items():
    if "orwidth_chase5" not in name and not name.startswith("in_tr"):
      continue
    if s.get("windows", 0) == 0:
      continue
    lines.append(
      f"| {name} | {s.get('pct_profitable')}% | {s.get('avg_compound_pct')}% | "
      f"{s.get('worst_compound_pct')}% | {s.get('historical_bad_avg_compound')}% | {s.get('worst_min_day_pct')}% |"
    )
  lines.append("")
  lines.append("**Break points (worst windows):**")
  for w in sorted(report.get("windows") or [], key=lambda x: min(
    (x.get("results") or {}).get("in_tr10_orwidth_chase5_75x", {}).get("compound_total_pct", 999)
  ))[:6]:
    tr = (w.get("results") or {}).get("in_tr10_orwidth_chase5_75x", {})
    if not tr:
      continue
    lines.append(
      f"- [{w.get('label')}] {w['start']}->{w['end']} NIFTY {w.get('nifty_return_pct')}% "
      f"({w.get('bar_interval','auto')}) compound {tr.get('compound_total_pct')}% min-day {tr.get('min_daily_return_pct')}%"
    )
  block = "\n".join(lines)
  if LOG_START not in text:
    text += f"\n## OR-width stress test\n\n{LOG_START}\n(pending)\n{LOG_END}\n"
  pre, rest = text.split(LOG_START, 1)
  _, post = rest.split(LOG_END, 1)
  log_path.write_text(f"{pre}{LOG_START}\n{block}\n{LOG_END}{post}", encoding="utf-8")
  print(f"Updated: {log_path}")


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--window-days", type=int, default=15)
  ap.add_argument("--bad", type=int, default=5)
  ap.add_argument("--good", type=int, default=3)
  ap.add_argument("--random", type=int, default=8)
  ap.add_argument("--historical-bad", type=int, default=5, help="worst 15d NIFTY windows on 1h bars (pre-Jun-2026)")
  ap.add_argument("--seed", type=int, default=42)
  ap.add_argument("--end", type=str, default="")
  ap.add_argument("--resume", action="store_true")
  ap.add_argument("--prefetch", action="store_true")
  ap.add_argument("--leverage-push", action="store_true", help="also sweep max_leverage 50-150x")
  args = ap.parse_args()

  ist = ZoneInfo("Asia/Kolkata")
  end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else datetime.now(ist).date()
  while end.weekday() >= 5:
    end -= timedelta(days=1)
  floor_5m = end - timedelta(days=55)

  configs = _configs_for_run(args.leverage_push)

  report: dict | None = None
  start_idx = 0
  if args.resume and CHECKPOINT_PATH.exists():
    report = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    done = sum(1 for w in report.get("windows") or [] if w.get("results"))
    start_idx = done
    print(f"Resuming from window {start_idx + 1}/{len(report['windows'])}")
  else:
    windows = _pick_windows(
      floor_5m=floor_5m,
      end=end,
      n_sessions=args.window_days,
      n_bad=args.bad,
      n_good=args.good,
      n_random=args.random,
      n_historical_bad=args.historical_bad,
      seed=args.seed,
    )
    report = {
      "generated_at": datetime.now(ist).isoformat(),
      "window_sessions": args.window_days,
      "intraday_floor_5m": floor_5m.isoformat(),
      "end_date": end.isoformat(),
      "configs": configs,
      "windows": windows,
      "summary": {},
    }

  if args.prefetch:
    CHECKPOINT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    subprocess.run(
      [sys.executable, str(ROOT / "scripts" / "prefetch_intraday_cache.py"), "--from-report", str(CHECKPOINT_PATH)],
      check=False,
    )

  windows = report["windows"]
  print(
    f"OR-width stress | {len(windows)} windows | from #{start_idx + 1} | "
    f"{len(configs)} configs | hist_bad={args.historical_bad}"
  )

  for wi in range(start_idx, len(windows)):
    win = windows[wi]
    if win.get("results") and not args.leverage_push:
      continue
    print(
      f"[{wi + 1}/{len(windows)}] {win['label']} {win['start']} -> {win['end']} "
      f"NIFTY {win.get('nifty_return_pct')}% bars={win.get('bar_interval','auto')}",
      flush=True,
    )
    win.setdefault("results", {})
    for cfg in configs:
      name = cfg["name"]
      if name in win["results"] and not args.leverage_push:
        continue
      kw = {k: v for k, v in cfg.items() if k != "name"}
      if win.get("bar_interval"):
        kw["bar_interval"] = win["bar_interval"]
      print(f"  {name} ...", flush=True)
      win["results"][name] = compound._eval_compound(name, win["sessions"], kw)
    report["generated_at"] = datetime.now(ist).isoformat()
    _save_checkpoint(report)

  report["summary"] = {c["name"]: _summarize_config(windows, c["name"]) for c in configs}
  REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
  _patch_log(report)

  print("\n=== SUMMARY (hero configs) ===")
  for name in ("in_tr10_orwidth_chase5_75x", "in_tr8_orwidth_chase5_75x"):
    s = report["summary"].get(name, {})
    if s:
      print(
        f"{name}: {s['windows_profitable']}/{s['windows']} profitable | avg {s['avg_compound_pct']}% | "
        f"worst {s['worst_compound_pct']}% | hist-bad avg {s['historical_bad_avg_compound']}%"
      )
  if args.leverage_push:
    print("\n=== LEVERAGE PUSH (tr10) ===")
    for lev in LEVERAGE_PUSH:
      n = f"in_tr10_orwidth_chase5_{int(lev)}x"
      s = report["summary"].get(n, {})
      if s:
        print(f"  {lev}x: avg {s.get('avg_compound_pct')}% worst {s.get('worst_compound_pct')}% min-day {s.get('worst_min_day_pct')}%")
  print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
  main()
