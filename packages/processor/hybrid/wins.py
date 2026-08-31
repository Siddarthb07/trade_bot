"""Honest wins celebration — lane-labeled milestones."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
WINS_PATH = ROOT / "models" / "hybrid_wins.jsonl"

LANE_DISCLAIMER = {
  "product": "Product lane — risk-capped, paper/live-eligible path.",
  "stretch": "Stretch lane — higher risk budget; not default live.",
  "research": "Research / not live-eligible — lottery hero or unguarded sim.",
}


def _now() -> str:
  return datetime.now(timezone.utc).isoformat()


def append_win(row: dict[str, Any]) -> dict[str, Any]:
  WINS_PATH.parent.mkdir(parents=True, exist_ok=True)
  lane = str(row.get("lane") or "product")
  payload = {
    **row,
    "ts": row.get("ts") or _now(),
    "disclaimer": LANE_DISCLAIMER.get(lane, LANE_DISCLAIMER["product"]),
  }
  with WINS_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(payload, default=str) + "\n")
  return payload


def list_wins(limit: int = 40) -> list[dict[str, Any]]:
  if not WINS_PATH.exists():
    return []
  lines = WINS_PATH.read_text(encoding="utf-8").strip().splitlines()
  out: list[dict[str, Any]] = []
  for line in lines[-limit:]:
    try:
      out.append(json.loads(line))
    except json.JSONDecodeError:
      continue
  return list(reversed(out))


def detect_wins_from_run(
  *,
  lane: str,
  asof: str | None,
  window_id: str | None,
  compound_pct: float,
  worst_day_pct: float,
  best_day_pct: float,
  primary_score: float,
  prev_best_primary: float | None,
  prev_equity_high: float | None,
  final_capital: float,
  start_capital: float,
  beats_ceiling: bool,
  gap_to_ceiling_pct: float | None,
  trade_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
  """Emit milestone wins. Research spikes are celebrated but labeled."""
  wins: list[dict[str, Any]] = []
  base = {
    "lane": lane,
    "asof": asof,
    "window_id": window_id,
    "metrics": {
      "compound_pct": compound_pct,
      "worst_day_pct": worst_day_pct,
      "best_day_pct": best_day_pct,
      "primary_score": primary_score,
      "final_capital": final_capital,
    },
    "trade_ids": trade_ids or [],
    "north_star": "most_profits",
  }

  if best_day_pct >= 5.0:
    kind = "best_day"
    title = f"Strong day +{best_day_pct:.1f}%"
    if lane == "research":
      title = f"Research spike +{best_day_pct:.1f}%"
    wins.append(append_win({**base, "kind": kind, "title": title}))

  if prev_best_primary is not None and primary_score > prev_best_primary + 0.01:
    wins.append(
      append_win(
        {
          **base,
          "kind": "primary_score_pr",
          "title": f"Primary score PR {primary_score:.2f} (was {prev_best_primary:.2f})",
        }
      )
    )

  if prev_equity_high is not None and final_capital > prev_equity_high:
    wins.append(
      append_win(
        {
          **base,
          "kind": "equity_high",
          "title": f"New equity high ₹{final_capital:,.0f}",
        }
      )
    )
  elif prev_equity_high is None and final_capital > start_capital:
    wins.append(
      append_win(
        {
          **base,
          "kind": "equity_up",
          "title": f"Equity up to ₹{final_capital:,.0f}",
        }
      )
    )

  if beats_ceiling and lane in ("stretch", "product"):
    wins.append(
      append_win(
        {
          **base,
          "kind": "beat_ceiling",
          "title": "Beat aspiration ceiling (risk-gated)",
        }
      )
    )
  elif beats_ceiling and lane == "research":
    wins.append(
      append_win(
        {
          **base,
          "kind": "research_ceiling",
          "title": "Research matched/beat ceiling fixture",
        }
      )
    )

  if gap_to_ceiling_pct is not None and gap_to_ceiling_pct < 10 and compound_pct > 0 and lane != "research":
    wins.append(
      append_win(
        {
          **base,
          "kind": "ceiling_gap_close",
          "title": f"Within {gap_to_ceiling_pct:.1f}pp of ceiling",
        }
      )
    )

  if window_id == "july_chop" and compound_pct > 0 and worst_day_pct > -8:
    wins.append(
      append_win(
        {
          **base,
          "kind": "survived_july",
          "title": f"Survived July chop +{compound_pct:.1f}%",
        }
      )
    )

  return wins
