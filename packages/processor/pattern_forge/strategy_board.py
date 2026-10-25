"""Build strategy ending-capital comparison for Pattern Lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PF = ROOT / "models" / "pattern_forge"

MONTH_ORDER = [
  "january",
  "february",
  "march",
  "april",
  "may",
  "june",
  "july",
  "august",
  "september",
  "october",
  "november",
  "december",
]
MONTH_SHORT = {
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


def _load(path: Path) -> dict[str, Any] | None:
  if not path.exists():
    return None
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return None
  return data if isinstance(data, dict) else None


def normalize_months(report: dict[str, Any]) -> list[dict[str, Any]]:
  rows = list(report.get("months") or [])
  by_name = {str(m.get("month") or "").lower(): m for m in rows}
  out: list[dict[str, Any]] = []
  for i, name in enumerate(MONTH_ORDER):
    m = by_name.get(name)
    if not m:
      # try YYYY-MM
      key = f"2025-{i + 1:02d}"
      m = next((r for r in rows if str(r.get("month") or "").startswith(key)), None)
    if not m:
      continue
    start = float(m.get("capital_start") or 0)
    end = float(m.get("capital_end") or 0)
    pnl = round(end - start, 2)
    out.append(
      {
        "month": name,
        "label": MONTH_SHORT[name],
        "month_num": i + 1,
        "capital_start": start,
        "capital_end": end,
        "pnl": pnl,
        "month_return_pct": float(m.get("month_return_pct") or 0),
        "n_trades": int(m.get("n_trades") or 0),
        "wins": int(m.get("wins") or 0),
      }
    )
  return out


def strategy_card(report: dict[str, Any], *, role: str) -> dict[str, Any]:
  start = float(report.get("capital_start") or 10_000)
  end = float(report.get("capital_end") or start)
  months = normalize_months(report)
  worst_pnl = min((m["pnl"] for m in months), default=0.0)
  best_pnl = max((m["pnl"] for m in months), default=0.0)
  year_pnl = round(end - start, 2)
  return {
    "role": role,
    "lane": report.get("lane") or report.get("strategy") or role,
    "run_id": report.get("run_id"),
    "capital_start": start,
    "capital_end": round(end, 2),
    "year_pnl": year_pnl,
    "total_return_pct": float(report.get("total_return_pct") or (100.0 * year_pnl / start if start else 0)),
    "green_months": int(report.get("green_months") or sum(1 for m in months if m["pnl"] > 0)),
    "months_total": int(report.get("months_total") or len(months)),
    "worst_month_pct": float(report.get("worst_month_pct") or (min((m["month_return_pct"] for m in months), default=0))),
    "best_month_pct": float(report.get("best_month_pct") or (max((m["month_return_pct"] for m in months), default=0))),
    "worst_month_pnl": worst_pnl,
    "best_month_pnl": best_pnl,
    "loss_lte_profits": abs(min(0.0, worst_pnl)) <= max(0.0, year_pnl),
    "months": months,
    "knobs": report.get("knobs") or {},
    "n_trades": report.get("n_trades"),
    "goal_met": report.get("goal_met"),
  }


def load_stretch_panel() -> dict[str, Any] | None:
  """Stretch-lane survivor panel (guard_omega_d) for Pattern Lab."""
  stretch_path = PF / "v2_4_stretch_latest.json"
  omega_path = PF / "guard_h_omega.json"
  meta = _load(stretch_path)
  if not meta:
    return None
  years: list[dict[str, Any]] = []
  omega = _load(omega_path)
  if omega:
    for row in omega.get("full_panel") or []:
      if row.get("name") == "guard_omega_d":
        years = list(row.get("years") or [])
        break
    if not years and (omega.get("best") or {}).get("name") == "guard_omega_d":
      years = list((omega.get("best") or {}).get("years") or [])
  summary = dict(meta.get("full_panel_summary") or {})
  if not summary and years:
    summary = {
      "years_positive": sum(1 for y in years if float(y.get("total_return_pct") or 0) > 0),
      "sum_pnl": round(sum(float(y.get("capital_end") or 10_000) - 10_000 for y in years), 2),
    }
  return {
    "variant": meta.get("variant") or "guard_omega_d",
    "lane": meta.get("lane") or "v2_4_stretch",
    "claim": meta.get("claim"),
    "nine_nine": bool(meta.get("nine_nine")),
    "locked_v2_untouched": bool(meta.get("locked_v2_untouched")),
    "summary": summary,
    "years": [
      {
        "year": int(y.get("year") or 0),
        "label": str(y.get("year") or "")[2:],
        "return_pct": float(y.get("total_return_pct") or 0),
        "worst_month_pct": float(y.get("worst_month_pct") or 0),
        "n_trades": int(y.get("n_trades") or 0),
        "capital_end": float(y.get("capital_end") or 0),
      }
      for y in years
    ],
    "chart": [
      {
        "name": str(y.get("year") or "")[2:],
        "ret": float(y.get("total_return_pct") or 0),
        "fill": "#bf5af2" if float(y.get("total_return_pct") or 0) >= 700 else "#30d158",
      }
      for y in years
    ],
  }


def load_strategy_board(capital: float = 10_000.0) -> dict[str, Any]:
  """Named lanes for the ending-capital chart."""
  files = [
    ("v2", PF / "v2_latest.json"),
    ("v2_1", PF / "v2_1_latest.json"),
    ("v3", PF / "v3_latest.json"),
    ("aim_next", PF / "v2_aim_next_latest.json"),
    ("aim40", PF / "v2_aim40_latest.json"),
    ("product_lev3", PF / "v2_product_latest.json"),
  ]
  # Also fold leverage sweep if present
  sweep = _load(PF / "aim40_leverage_sweep.json")
  strategies: list[dict[str, Any]] = []
  seen: set[str] = set()

  for role, path in files:
    rep = _load(path)
    if not rep or int(rep.get("months_total") or 0) < 12:
      continue
    card = strategy_card(rep, role=role)
    key = str(card["lane"])
    if key in seen:
      continue
    seen.add(key)
    strategies.append(card)

  if sweep and isinstance(sweep.get("rows"), list):
    for row in sweep["rows"]:
      lev = row.get("lev")
      lane = f"sweep_lev{lev}"
      if lane in seen:
        continue
      # Reconstruct thin card from sweep row + matching benchmark if any
      start = capital
      ret = float(row.get("total_return_pct") or 0)
      end = round(start * (1 + ret / 100.0), 2)
      strategies.append(
        {
          "role": "sweep",
          "lane": lane,
          "run_id": row.get("run_id"),
          "capital_start": start,
          "capital_end": end,
          "year_pnl": round(end - start, 2),
          "total_return_pct": ret,
          "green_months": row.get("green_months"),
          "months_total": 12,
          "worst_month_pct": row.get("worst_month_pct"),
          "best_month_pct": row.get("best_month_pct"),
          "worst_month_pnl": None,
          "best_month_pnl": None,
          "loss_lte_profits": abs(float(row.get("worst_month_pct") or 0)) <= abs(ret) if ret > 0 else False,
          "months": [],
          "knobs": {"leverage": lev, "sleeve": row.get("sleeve")},
          "n_trades": row.get("n_trades"),
          "goal_met": row.get("goal_met_product"),
        }
      )
      seen.add(lane)

  strategies.sort(key=lambda s: float(s.get("capital_end") or 0), reverse=True)
  # Prefer locked v2 as hero; v2_1 is challenger only
  hero = next((s for s in strategies if s["role"] == "v2"), None) or next(
    (s for s in strategies if s["role"] in ("aim_next", "aim40", "product_lev3")),
    strategies[0] if strategies else None,
  )
  challenger = next((s for s in strategies if s["role"] == "v2_1"), None)
  ROLE_FILL = {
    "v2": "#30d158",
    "v2_1": "#64d2ff",
    "v3": "#ffd60a",
    "aim_next": "#bf5af2",
    "aim40": "#ff9f0a",
    "product_lev3": "#8e8e93",
  }
  equity_compare = []
  if hero and (hero.get("months") or []):
    for m in hero["months"]:
      equity_compare.append(
        {
          "month": m.get("label") or m.get("month"),
          "v2": m.get("capital_end"),
          "v2_1": None,
        }
      )
  if challenger and (challenger.get("months") or []):
    by_lab = {str(r.get("month")): r for r in equity_compare}
    for m in challenger["months"]:
      lab = m.get("label") or str(m.get("month") or "")[:3].title()
      row = by_lab.get(lab)
      if row is None:
        row = {"month": lab, "v2": None, "v2_1": m.get("capital_end")}
        equity_compare.append(row)
        by_lab[lab] = row
      else:
        row["v2_1"] = m.get("capital_end")
  stretch = load_stretch_panel()

  return {
    "capital_start": capital,
    "stretch_panel": stretch,
    "strategies": strategies,
    "chart": [
      {
        "name": s["lane"],
        "end": s["capital_end"],
        "pnl": s["year_pnl"],
        "ret": s["total_return_pct"],
        "fill": ROLE_FILL.get(str(s.get("role") or ""), "#30d158" if float(s.get("year_pnl") or 0) >= 0 else "#ff453a"),
      }
      for s in strategies
    ],
    "equity_compare": equity_compare,
    "hero_months": (hero or {}).get("months") or [],
    "hero_lane": (hero or {}).get("lane"),
    "challenger_lane": (challenger or {}).get("lane"),
  }
