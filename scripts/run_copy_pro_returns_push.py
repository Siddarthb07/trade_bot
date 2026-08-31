"""May–Aug returns push grid for copy_bulk_pro toward ≥10%/month hit-rate."""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
os.environ.setdefault(
  "POSTGRES_URL",
  "postgresql://smartmoney:changeme@127.0.0.1:5433/smartmoney",
)

from processor.day_sim import simulate_day
from processor.hybrid.registry import sim_kwargs_for_strategy
from processor.smart_money_gate import (
  bulk_data_coverage,
  copy_pro_should_sitout,
  cooldown_excludes,
  empty_copy_pro_cooldown,
  register_copy_pro_outcomes,
)

CAPITAL = 10_000.0
MONTHS = [
  ("may", "2026-05-01", "2026-05-31"),
  ("june", "2026-06-01", "2026-06-30"),
  ("july", "2026-07-01", "2026-07-31"),
  ("august", "2026-08-03", "2026-08-28"),
]
BASELINE_MEAN = -6.2  # approx May–Aug ablation mean
DD_CAP = 25.0
HIT_PCT = 10.0


def sessions(a: str, b: str) -> list[str]:
  sd, ed = date.fromisoformat(a), date.fromisoformat(b)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def base_kw() -> dict:
  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  return kw


def run_month(start: str, end: str, kw: dict, sl: int, ent: int, sit: int) -> dict:
  days = sessions(start, end)
  cap = CAPITAL
  cd = empty_copy_pro_cooldown()
  trades_out: list[dict] = []
  peak = cap
  max_dd = 0.0
  n_sit = 0
  n_flat = 0

  for asof in days:
    if copy_pro_should_sitout(cd):
      n_sit += 1
      cd = register_copy_pro_outcomes(
        cd, [], ticker_cooldown_days=sl, entity_cooldown_days=ent, sitout_after_sl_days=sit
      )
      continue
    ex_t, ex_e = cooldown_excludes(cd)
    res = simulate_day(
      asof=asof,
      capital=cap,
      currency="INR",
      market="IN",
      path_mode="session",
      allow_demo_fallback=False,
      exclude_tickers=ex_t or None,
      exclude_entities=ex_e or None,
      **kw,
    )
    end_cap = float(res.get("capital_end") or cap)
    day_trades = list(res.get("trades") or [])
    if not day_trades:
      n_flat += 1
    for t in day_trades:
      trades_out.append(
        {
          "asof": asof,
          "ticker": t.get("ticker"),
          "pnl": t.get("pnl"),
          "exit": t.get("exit_reason"),
          "margin_inr": t.get("slot_capital"),
          "invested_notional_inr": t.get("entry_notional") or t.get("money_put"),
        }
      )
    cd = register_copy_pro_outcomes(
      cd,
      day_trades,
      ticker_cooldown_days=sl,
      entity_cooldown_days=ent,
      sitout_after_sl_days=sit,
    )
    peak = max(peak, end_cap)
    max_dd = max(max_dd, 100.0 * (peak - end_cap) / peak if peak else 0.0)
    cap = end_cap

  wins = sum(1 for t in trades_out if float(t.get("pnl") or 0) > 0)
  losses = len(trades_out) - wins
  return {
    "compound_pct": round(100.0 * (cap - CAPITAL) / CAPITAL, 3),
    "pnl_inr": round(cap - CAPITAL, 2),
    "capital_end": round(cap, 2),
    "max_dd_pct": round(max_dd, 2),
    "n_trades": len(trades_out),
    "wins": wins,
    "losses": losses,
    "n_flat_days": n_flat,
    "n_sitout_days": n_sit,
  }


def cfg_label(c: dict) -> str:
  trail = c.get("trail")
  t = "off" if not trail else f"arm{int(trail[0]*1000)}_tr{int(trail[1]*1000)}"
  slot = "1" if int(c.get("max_positions") or 1) == 1 else "sel2"
  return f"use{int(c['use']*100)}_trail{t}_sit{c['sit']}_slot{slot}"


def build_wave1() -> list[dict]:
  """Sizing × trail with sit=0 (ablation cooldowns already on)."""
  out = []
  for use in (0.6, 0.75, 0.85):
    for trail in (None, (0.015, 0.01), (0.025, 0.01)):
      out.append(
        {
          "use": use,
          "trail": trail,
          "sit": 0,
          "max_positions": 1,
          "bulk_second_min_wr": None,
          "bulk_second_min_score_gap": None,
        }
      )
  return out


def build_sit_wave(seeds: list[dict]) -> list[dict]:
  """Mild 1-day post-SL sitout on top seeds only."""
  out = []
  for s in seeds:
    c = dict(s["params"])
    c["sit"] = 1
    out.append(c)
  return out


def build_second_slot(seeds: list[dict]) -> list[dict]:
  out = []
  for s in seeds[:4]:
    p = s["params"]
    out.append(
      {
        "use": p["use"],
        "trail": p.get("trail"),
        "sit": 0,
        "max_positions": 2,
        "bulk_second_min_wr": 0.65,
        "bulk_second_min_score_gap": 0.5,
      }
    )
  return out


def apply_cfg(base: dict, c: dict) -> tuple[dict, int, int, int]:
  kw = deepcopy(base)
  sl = int(kw.pop("sl_cooldown_days", 1) or 1)
  ent = int(kw.pop("entity_cooldown_days", 1) or 1)
  kw.pop("sitout_after_sl_days", None)
  kw["capital_use_frac"] = float(c["use"])
  kw["max_positions"] = int(c.get("max_positions") or 1)
  if c.get("trail"):
    kw["soft_trail_arm_pct"] = float(c["trail"][0])
    kw["soft_trail_pct"] = float(c["trail"][1])
  else:
    kw.pop("soft_trail_arm_pct", None)
    kw.pop("soft_trail_pct", None)
  if c.get("bulk_second_min_wr") is not None:
    kw["bulk_second_min_wr"] = float(c["bulk_second_min_wr"])
    kw["bulk_second_min_score_gap"] = float(c["bulk_second_min_score_gap"])
  else:
    kw.pop("bulk_second_min_wr", None)
    kw.pop("bulk_second_min_score_gap", None)
  return kw, sl, ent, int(c["sit"])


def evaluate(rows: list[dict]) -> dict:
  compounds = [float(m["compound_pct"]) for m in rows]
  dds = [float(m["max_dd_pct"]) for m in rows]
  hit = sum(1 for x in compounds if x >= HIT_PCT)
  return {
    "months_hit_10": hit,
    "mean_compound_pct": round(mean(compounds), 3) if compounds else None,
    "max_month_dd_pct": round(max(dds), 2) if dds else None,
    "best_month_pct": round(max(compounds), 3) if compounds else None,
    "gate_pass": hit >= 2 and (max(dds) if dds else 99) <= DD_CAP and mean(compounds) > BASELINE_MEAN,
  }


def run_configs(cfgs: list[dict], base: dict) -> list[dict]:
  results = []
  for c in cfgs:
    label = cfg_label(c)
    kw, sl, ent, sit = apply_cfg(base, c)
    print(f"\n===== CONFIG {label} =====", flush=True)
    month_rows: list[dict] = []

    def _one(name: str, start: str, end: str) -> dict:
      m = run_month(start, end, kw, sl, ent, sit)
      m["month"] = name
      return m

    with ThreadPoolExecutor(max_workers=4) as pool:
      futs = {pool.submit(_one, n, a, b): n for n, a, b in MONTHS}
      by_name = {futs[f]: f.result() for f in as_completed(futs)}
    for name, _, _ in MONTHS:
      m = by_name[name]
      month_rows.append(m)
      print(
        f"  {name}: {m['compound_pct']:+.2f}% dd={m['max_dd_pct']:.1f}% "
        f"trades={m['n_trades']} sit={m['n_sitout_days']}",
        flush=True,
      )
    ev = evaluate(month_rows)
    results.append(
      {
        "id": label,
        "params": c,
        "months": month_rows,
        **ev,
      }
    )
    print(
      f">>> {label} hit10={ev['months_hit_10']}/4 mean={ev['mean_compound_pct']}% "
      f"maxDD={ev['max_month_dd_pct']}% gate={ev['gate_pass']}",
      flush=True,
    )
  return results


def _rank_key(r: dict) -> tuple:
  return (
    int(r["gate_pass"]),
    r["months_hit_10"],
    r["mean_compound_pct"] or -999,
    -(r["max_month_dd_pct"] or 99),
  )


def main() -> None:
  cov = bulk_data_coverage(since="2026-05-01")
  print("bulk_coverage", cov, flush=True)
  base = base_kw()
  print(
    "base",
    {
      k: base[k]
      for k in ("filter_mode", "capital_use_frac", "bulk_wr_pseudo_n", "bulk_lookback_sessions")
      if k in base
    },
    flush=True,
  )

  wave1 = run_configs(build_wave1(), base)
  all_rows = list(wave1)
  any_pass = any(r["gate_pass"] for r in all_rows)

  sit_rows: list[dict] = []
  if not any_pass:
    seeds = sorted(wave1, key=_rank_key, reverse=True)[:3]
    print("\n===== WAVE2 sitout=1 on top-3 seeds =====", flush=True)
    sit_rows = run_configs(build_sit_wave(seeds), base)
    all_rows.extend(sit_rows)
    any_pass = any(r["gate_pass"] for r in all_rows)

  second: list[dict] = []
  if not any_pass:
    seeds = sorted(all_rows, key=_rank_key, reverse=True)[:4]
    print("\n===== WAVE3 selective 2nd-slot =====", flush=True)
    second = run_configs(build_second_slot(seeds), base)
    all_rows.extend(second)

  ranked = sorted(all_rows, key=_rank_key, reverse=True)
  best = ranked[0] if ranked else None
  promoted = None
  if best and best["gate_pass"]:
    promoted = {
      "id": best["id"],
      "capital_use_frac": best["params"]["use"],
      "soft_trail_arm_pct": best["params"]["trail"][0] if best["params"].get("trail") else None,
      "soft_trail_pct": best["params"]["trail"][1] if best["params"].get("trail") else None,
      "sitout_after_sl_days": best["params"]["sit"],
      "max_positions": best["params"].get("max_positions", 1),
      "bulk_second_min_wr": best["params"].get("bulk_second_min_wr"),
      "bulk_second_min_score_gap": best["params"].get("bulk_second_min_score_gap"),
    }

  out = {
    "generated_at": date.today().isoformat(),
    "goal": {"months_ge_10_min": 2, "max_month_dd_pct": DD_CAP, "mean_gt_baseline": BASELINE_MEAN},
    "bulk_coverage": cov,
    "wave1_n": len(wave1),
    "sit_wave_n": len(sit_rows),
    "second_slot_n": len(second),
    "results": all_rows,
    "ranked_ids": [r["id"] for r in ranked],
    "best": best,
    "promoted": promoted,
    "ceiling": {
      "best_id": best["id"] if best else None,
      "best_mean_compound_pct": best["mean_compound_pct"] if best else None,
      "best_months_hit_10": best["months_hit_10"] if best else None,
      "best_month_pct": best["best_month_pct"] if best else None,
      "best_max_dd_pct": best["max_month_dd_pct"] if best else None,
      "gate_cleared": bool(promoted),
    },
  }
  path = ROOT / "models" / "copy_pro_returns_push.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print("\n===== CEILING =====", flush=True)
  print(json.dumps(out["ceiling"], indent=2), flush=True)
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
