"""Pattern Forge decision / trade / choice ledger — append-only JSONL for the dash."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LEDGER_DIR = ROOT / "models" / "pattern_forge"
DECISIONS_PATH = LEDGER_DIR / "decisions.jsonl"
TRADES_PATH = LEDGER_DIR / "trades.jsonl"
RUNS_PATH = LEDGER_DIR / "runs.jsonl"
ITERATIONS_PATH = LEDGER_DIR / "iterations.jsonl"
LATEST_SUMMARY = LEDGER_DIR / "latest_summary.json"


def _now() -> str:
  return datetime.now(timezone.utc).isoformat()


def _append(path: Path, row: dict[str, Any]) -> dict[str, Any]:
  path.parent.mkdir(parents=True, exist_ok=True)
  out = {**row, "ts": row.get("ts") or _now()}
  with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(out, default=str) + "\n")
  return out


def log_decision(row: dict[str, Any]) -> dict[str, Any]:
  """One fire/skip/choice for a ticker on a session day."""
  return _append(
    DECISIONS_PATH,
    {
      "kind": "decision",
      "asof": row.get("asof"),
      "ticker": row.get("ticker"),
      "family": row.get("family"),
      "run_id": row.get("run_id"),
      "iteration_id": row.get("iteration_id"),
      "choice": row.get("choice"),  # fire | skip | sitout | no_ruin
      "primary": row.get("primary"),
      "swarm_agreement": row.get("swarm_agreement"),
      "swarm_messages": row.get("swarm_messages"),
      "no_ruin": row.get("no_ruin"),
      "skip_reason": row.get("skip_reason"),
      "notes": row.get("notes") or [],
      "disclaimer": "Paper/sim audit — not investment advice.",
    },
  )


def log_trade(row: dict[str, Any]) -> dict[str, Any]:
  return _append(
    TRADES_PATH,
    {
      "kind": "trade",
      **row,
      "disclaimer": "Paper/sim trade — not investment advice.",
    },
  )


def log_run(row: dict[str, Any]) -> dict[str, Any]:
  return _append(RUNS_PATH, {"kind": "run", **row})


def log_iteration(row: dict[str, Any]) -> dict[str, Any]:
  return _append(ITERATIONS_PATH, {"kind": "iteration", **row})


def write_summary(summary: dict[str, Any]) -> dict[str, Any]:
  LEDGER_DIR.mkdir(parents=True, exist_ok=True)
  out = {**summary, "updated_at": _now()}
  LATEST_SUMMARY.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  return out


def _tail_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
  if not path.exists():
    return []
  lines = path.read_text(encoding="utf-8").strip().splitlines()
  out: list[dict[str, Any]] = []
  for line in lines[-limit:]:
    try:
      out.append(json.loads(line))
    except Exception:
      continue
  out.reverse()
  return out


def recent_decisions(limit: int = 200) -> list[dict[str, Any]]:
  return _tail_jsonl(DECISIONS_PATH, limit)


def recent_trades(limit: int = 200) -> list[dict[str, Any]]:
  return _tail_jsonl(TRADES_PATH, limit)


def recent_runs(limit: int = 50) -> list[dict[str, Any]]:
  return _tail_jsonl(RUNS_PATH, limit)


def recent_iterations(limit: int = 50) -> list[dict[str, Any]]:
  return _tail_jsonl(ITERATIONS_PATH, limit)


def load_summary() -> dict[str, Any]:
  if not LATEST_SUMMARY.exists():
    return {"status": "empty", "claim": "No Pattern Forge run yet."}
  try:
    return json.loads(LATEST_SUMMARY.read_text(encoding="utf-8"))
  except Exception:
    return {"status": "corrupt"}


def month_rollup_from_trades(year: int = 2025) -> list[dict[str, Any]]:
  """Aggregate trades JSONL into calendar months for a year."""
  if not TRADES_PATH.exists():
    return []
  months: dict[str, dict[str, Any]] = {}
  for line in TRADES_PATH.read_text(encoding="utf-8").splitlines():
    try:
      t = json.loads(line)
    except Exception:
      continue
    asof = str(t.get("asof") or t.get("entry_date") or "")[:10]
    if not asof.startswith(str(year)):
      continue
    key = asof[:7]
    m = months.setdefault(
      key,
      {"month": key, "pnl": 0.0, "n_trades": 0, "wins": 0, "losses": 0},
    )
    pnl = float(t.get("pnl") or 0)
    m["pnl"] = round(m["pnl"] + pnl, 2)
    m["n_trades"] += 1
    if pnl > 0:
      m["wins"] += 1
    elif pnl < 0:
      m["losses"] += 1
  return [months[k] for k in sorted(months.keys())]
