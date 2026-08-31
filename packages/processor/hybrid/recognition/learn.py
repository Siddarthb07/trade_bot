"""Self-learning loop — updates agent weights + meta bias from outcomes and chat lessons.

Deterministic, file-backed. No LLM on the fire path; chat lessons only nudge knobs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STATE_PATH = ROOT / "models" / "godfather_learn_state.json"

DEFAULT_WEIGHTS: dict[str, float] = {
  "Geometry": 0.6,
  "Regime": 1.1,
  "Similarity": 1.0,
  "LineGeometry": 1.0,
  "MetaLabel": 1.35,
  "Cost": 1.4,
  "Decay": 0.9,
  "Changepoint": 1.0,
  "Hurst": 1.0,
  "JumpRisk": 1.15,
  "GHLZ": 1.0,
  "ORBQuality": 1.1,
  "Momentum": 0.95,
  "SessionClock": 0.85,
  "Breadth": 0.9,
  "VolRegime": 1.05,
  "OutcomeLearner": 1.2,
  "RulesClerk": 1.5,
  "VPIN": 0.85,
  "Hawkes": 0.85,
  "Kyle": 0.85,
}

W_MIN, W_MAX = 0.35, 2.75


def _clamp(w: float) -> float:
  return float(max(W_MIN, min(W_MAX, w)))


def default_state() -> dict[str, Any]:
  return {
    "schema_version": 1,
    "project": "godfather",
    "updated_at": None,
    "n_outcome_updates": 0,
    "n_chat_lessons": 0,
    "tau": 0.50,
    "meta_bias": 0.0,
    "fleet_bias": 0.0,
    "recent_skip_rate": 0.5,
    "recent_outcomes": [],  # last N {asof, pnl, win}
    "agent_weights": dict(DEFAULT_WEIGHTS),
    "agent_stats": {},  # name -> {correct, wrong, takes_when_win, ...}
    "hit_rates": {"trend_up": 0.62, "failed_break": 0.28, "chop": 0.40},
    "lessons": [],
    "rules": [],
    "n_rules": 0,
    "n_hard_rules": 0,
    "notes": "Online weights + rules ledger from daily P&L. Read briefing before every fire.",
  }


def state_path(path: Path | None = None) -> Path:
  return path or DEFAULT_STATE_PATH


def load_state(path: Path | None = None) -> dict[str, Any]:
  p = state_path(path)
  if not p.exists():
    return default_state()
  try:
    data = json.loads(p.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return default_state()
  base = default_state()
  base.update({k: v for k, v in data.items() if k in base or k in data})
  weights = dict(DEFAULT_WEIGHTS)
  weights.update(data.get("agent_weights") or {})
  base["agent_weights"] = {k: _clamp(float(v)) for k, v in weights.items()}
  return base


def save_state(state: dict[str, Any], path: Path | None = None) -> Path:
  p = state_path(path)
  p.parent.mkdir(parents=True, exist_ok=True)
  state = dict(state)
  state["updated_at"] = datetime.now(timezone.utc).isoformat()
  p.write_text(json.dumps(state, indent=2), encoding="utf-8")
  return p


def agent_weight(state: dict[str, Any], name: str) -> float:
  return float((state.get("agent_weights") or {}).get(name, DEFAULT_WEIGHTS.get(name, 1.0)))


def _bump_stat(state: dict[str, Any], agent: str, field: str, delta: float = 1.0) -> None:
  stats = state.setdefault("agent_stats", {})
  row = stats.setdefault(agent, {"correct": 0.0, "wrong": 0.0})
  row[field] = float(row.get(field) or 0.0) + delta


def apply_outcome(
  state: dict[str, Any],
  *,
  asof: str,
  messages: list[dict[str, Any]] | None,
  pnl: float,
  traded: bool,
  skip_reason: str | None = None,
  trades: list[dict[str, Any]] | None = None,
  regime_label: str | None = None,
) -> dict[str, Any]:
  """Update weights + mine rules ledger from one session outcome."""
  from processor.hybrid.recognition.rules_ledger import (
    daily_briefing,
    merge_mined_into_state,
    mine_rules_from_day,
  )

  msgs = list(messages or [])
  win = bool(traded and pnl > 0)
  loss = bool(traded and pnl < 0)
  skipped = not traded

  recent = list(state.get("recent_outcomes") or [])
  recent.append(
    {
      "asof": asof,
      "pnl": round(float(pnl), 4),
      "traded": traded,
      "win": win if traded else None,
      "skip_reason": skip_reason,
      "regime": regime_label,
      "tickers": [str(t.get("ticker")) for t in (trades or []) if t.get("ticker")],
      "exits": [str(t.get("exit_reason")) for t in (trades or []) if t.get("exit_reason")],
    }
  )
  state["recent_outcomes"] = recent[-40:]

  last = state["recent_outcomes"][-20:]
  if last:
    state["recent_skip_rate"] = round(sum(1 for r in last if not r.get("traded")) / len(last), 4)

  fills = [r for r in state["recent_outcomes"] if r.get("traded")]
  if fills:
    state["fleet_bias"] = round(
      sum(1.0 if r.get("win") else -1.0 for r in fills[-12:]) / min(12, len(fills)),
      4,
    )

  weights = dict(state.get("agent_weights") or DEFAULT_WEIGHTS)

  if traded:
    for m in msgs:
      name = str(m.get("agent") or "")
      vote = str(m.get("vote") or "annotate")
      if vote not in ("take", "skip") or not name:
        continue
      w = float(weights.get(name, 1.0))
      if win:
        if vote == "take":
          weights[name] = _clamp(w * 1.06)
          _bump_stat(state, name, "correct")
        elif vote == "skip":
          weights[name] = _clamp(w * 0.96)
          _bump_stat(state, name, "wrong")
      elif loss:
        if vote == "take":
          weights[name] = _clamp(w * 0.94)
          _bump_stat(state, name, "wrong")
        elif vote == "skip":
          weights[name] = _clamp(w * 1.05)
          _bump_stat(state, name, "correct")

    mb = float(state.get("meta_bias") or 0.0)
    if win:
      state["meta_bias"] = round(max(-0.15, mb + 0.01), 4)
    elif loss:
      state["meta_bias"] = round(min(0.15, mb - 0.015), 4)

    tau = float(state.get("tau") or 0.55)
    if loss:
      state["tau"] = round(min(0.56, tau + 0.008), 4)
    elif win:
      state["tau"] = round(max(0.48, tau - 0.006), 4)

    for m in msgs:
      if m.get("agent") != "Similarity":
        continue
      payload = m.get("payload") or {}
      aid = payload.get("analog_id")
      if not aid:
        continue
      hrs = dict(state.get("hit_rates") or {})
      cur = float(hrs.get(str(aid), 0.5))
      if win:
        hrs[str(aid)] = round(min(0.85, cur + 0.02), 4)
      elif loss:
        hrs[str(aid)] = round(max(0.15, cur - 0.03), 4)
      state["hit_rates"] = hrs

  elif skipped:
    for name in ("Decay", "OutcomeLearner", "MetaLabel"):
      w = float(weights.get(name, 1.0))
      weights[name] = _clamp(w * 1.01)

  state["agent_weights"] = weights
  state["n_outcome_updates"] = int(state.get("n_outcome_updates") or 0) + 1

  mined = mine_rules_from_day(
    asof=asof,
    traded=traded,
    pnl=pnl,
    trades=trades,
    messages=msgs,
    regime_label=regime_label,
    skip_reason=skip_reason,
  )
  if mined:
    state = merge_mined_into_state(state, mined)
  daily_briefing(state, asof=asof)
  return state


_LESSON_PATTERNS: list[tuple[re.Pattern[str], dict[str, Any]]] = [
  (re.compile(r"more\s+selective|skip\s+more|raise\s+tau|stricter", re.I), {"tau_delta": 0.03, "meta_bias_delta": -0.02}),
  (re.compile(r"less\s+selective|trade\s+more|lower\s+tau|looser", re.I), {"tau_delta": -0.03, "meta_bias_delta": 0.02}),
  (re.compile(r"trust\s+regime|regime\s+matter", re.I), {"weight_boost": {"Regime": 1.08}}),
  (re.compile(r"cut\s+losers|tighter\s+stop|stop\s+loss", re.I), {"note": "prefer_tighter_sl"}),
  (re.compile(r"take\s+profit|lock\s+wins|tp\b", re.I), {"note": "prefer_take_profit"}),
  (re.compile(r"avoid\s+chop|chop\s+bad", re.I), {"weight_boost": {"Regime": 1.06, "Hurst": 1.05}, "meta_bias_delta": -0.01}),
  (re.compile(r"jump|gap\s+risk", re.I), {"weight_boost": {"JumpRisk": 1.1}}),
  (re.compile(r"late\s+session|no\s+late", re.I), {"weight_boost": {"SessionClock": 1.12}}),
]


def ingest_lesson(state: dict[str, Any], text: str, *, source: str = "chat") -> dict[str, Any]:
  """Nudge knobs from a free-text lesson (conversation / operator note)."""
  text = (text or "").strip()
  if not text:
    return state

  applied: list[str] = []
  for pat, adj in _LESSON_PATTERNS:
    if not pat.search(text):
      continue
    if "tau_delta" in adj:
      state["tau"] = round(max(0.4, min(0.8, float(state.get("tau") or 0.55) + adj["tau_delta"])), 4)
      applied.append(f"tau->{state['tau']}")
    if "meta_bias_delta" in adj:
      state["meta_bias"] = round(
        max(-0.2, min(0.2, float(state.get("meta_bias") or 0.0) + adj["meta_bias_delta"])),
        4,
      )
      applied.append(f"meta_bias->{state['meta_bias']}")
    if "weight_boost" in adj:
      weights = dict(state.get("agent_weights") or DEFAULT_WEIGHTS)
      for name, mult in adj["weight_boost"].items():
        weights[name] = _clamp(float(weights.get(name, 1.0)) * float(mult))
        applied.append(f"{name}*{mult}")
      state["agent_weights"] = weights
    if adj.get("note"):
      applied.append(str(adj["note"]))

  if not applied:
    applied.append("logged_only")

  lessons = list(state.get("lessons") or [])
  lessons.append(
    {
      "ts": datetime.now(timezone.utc).isoformat(),
      "source": source,
      "text": text[:500],
      "applied": applied,
    }
  )
  state["lessons"] = lessons[-50:]
  state["n_chat_lessons"] = int(state.get("n_chat_lessons") or 0) + 1
  return state


def learn_from_day_row(state: dict[str, Any], day: dict[str, Any]) -> dict[str, Any]:
  """Convenience: window/day dict from simulate_godfather_*."""
  rec = day.get("recognition") or {}
  regime = rec.get("regime") or day.get("regime") or {}
  return apply_outcome(
    state,
    asof=str(day.get("asof") or ""),
    messages=list(day.get("agents") or rec.get("messages") or []),
    pnl=float(day.get("realized_pnl") or day.get("pnl_inr") or 0.0),
    traded=int(day.get("n_trades") or 0) > 0,
    skip_reason=day.get("skip_reason"),
    trades=list(day.get("trades") or []),
    regime_label=str(regime.get("label") or "") or None,
  )


def agent_accuracy_map(state: dict[str, Any]) -> dict[str, float]:
  out: dict[str, float] = {}
  for name, row in (state.get("agent_stats") or {}).items():
    c = float(row.get("correct") or 0)
    w = float(row.get("wrong") or 0)
    if c + w <= 0:
      continue
    out[name] = round(c / (c + w), 4)
  return out
