"""Self-learning rules ledger — read before every session so mistakes don't repeat.

Flow:
  1. End of day → learn_from_session() analyzes P&L and writes/refreshes rules.
  2. Start of day → read_daily_briefing(asof) loads active rules (excludes / sit-out / policy).
  3. Engine must apply briefing excludes before ranking or sizing.

Standing claim: paper/sim learning only until a live gate exists.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = ROOT / "models" / "hybrid_rules_ledger.json"
HISTORY_PATH = ROOT / "models" / "hybrid_rules_history.jsonl"

# Defaults learned from Aug 24–28 failure trace (Elixir stale re-rank + SL double-tap).
DEFAULT_TICKER_COOLDOWN_SESSIONS = 2
DEFAULT_ENTITY_COOLDOWN_SESSIONS = 1
CONSECUTIVE_SL_SITOUT = 2  # after N SL days in a row → sit next session


def _now() -> str:
  return datetime.now(timezone.utc).isoformat()


def _empty() -> dict[str, Any]:
  return {
    "version": 1,
    "updated_at": None,
    "last_learned_asof": None,
    "last_briefing_asof": None,
    "last_briefing_at": None,
    "rules": [],
    "streak": {"sl_days": 0, "last_asof": None},
    "stats": {"learned_sessions": 0, "rules_fired": 0, "rules_created": 0},
  }


def load_rules_ledger() -> dict[str, Any]:
  if not RULES_PATH.exists():
    return _empty()
  try:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
  except Exception:
    return _empty()
  if not isinstance(data, dict):
    return _empty()
  base = _empty()
  base.update(data)
  base.setdefault("rules", [])
  base.setdefault("streak", {"sl_days": 0, "last_asof": None})
  base.setdefault("stats", {"learned_sessions": 0, "rules_fired": 0, "rules_created": 0})
  return base


def save_rules_ledger(state: dict[str, Any]) -> None:
  RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
  state = dict(state)
  state["updated_at"] = _now()
  RULES_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _append_history(event: dict[str, Any]) -> None:
  HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
  with HISTORY_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": _now(), **event}, default=str) + "\n")


def _session_dates_after(asof: str, n: int) -> str | None:
  """Return the date n weekday sessions after asof (exclusive of asof)."""
  if n <= 0:
    return asof
  d = date.fromisoformat(asof[:10])
  left = n
  while left > 0:
    d += timedelta(days=1)
    if d.weekday() < 5:
      left -= 1
  return d.isoformat()


def _is_expired(rule: dict[str, Any], asof: str) -> bool:
  if rule.get("permanent"):
    return False
  if str(rule.get("status") or "active") == "retired":
    return True
  exp = rule.get("expires_on")
  if not exp:
    return False
  try:
    return date.fromisoformat(asof[:10]) > date.fromisoformat(str(exp)[:10])
  except ValueError:
    return False


def active_rules(asof: str, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
  st = state or load_rules_ledger()
  out: list[dict[str, Any]] = []
  for r in st.get("rules") or []:
    if _is_expired(r, asof):
      continue
    if str(r.get("status") or "active") != "active":
      continue
    out.append(r)
  return out


def _upsert_rule(state: dict[str, Any], rule: dict[str, Any]) -> None:
  rules = list(state.get("rules") or [])
  rid = str(rule["id"])
  found = False
  for i, r in enumerate(rules):
    if str(r.get("id")) == rid:
      merged = {**r, **rule, "hits": int(r.get("hits") or 0) + 1, "updated_at": _now()}
      rules[i] = merged
      found = True
      break
  if not found:
    rule = {**rule, "hits": 1, "created_at": _now(), "updated_at": _now()}
    rules.append(rule)
    state["stats"]["rules_created"] = int(state["stats"].get("rules_created") or 0) + 1
  state["rules"] = rules


def seed_standing_policies(state: dict[str, Any] | None = None) -> dict[str, Any]:
  """One-time standing policies from known failure modes (always readable)."""
  st = state or load_rules_ledger()
  policies = [
    {
      "id": "policy_prior_session_lookback",
      "kind": "policy",
      "policy": "prior_session_lookback_only",
      "title": "Prior-session lookback only",
      "reason": "Stale bulk deals (e.g. QUADFUTURE disclosed Fri) were re-ranked Mon→Tue and double-tapped SL.",
      "status": "active",
      "permanent": True,
    },
    {
      "id": "policy_no_wr1_on_n2_monopoly",
      "kind": "policy",
      "policy": "shrink_low_n_win_rate",
      "title": "Shrink WR=1.0 on tiny n",
      "reason": "Elixir-class investors with WR=1.0 on n=2 + huge deal ₹ dominated ranker and lost.",
      "status": "active",
      "permanent": True,
    },
    {
      "id": "policy_read_rules_before_session",
      "kind": "policy",
      "policy": "require_daily_briefing",
      "title": "Read rules ledger before any session",
      "reason": "Self-learning loop: do not start ranking/sizing until briefing is loaded.",
      "status": "active",
      "permanent": True,
    },
  ]
  for p in policies:
    existing = next((r for r in st["rules"] if r.get("id") == p["id"]), None)
    if existing is None:
      _upsert_rule(st, p)
  save_rules_ledger(st)
  return st


def learn_from_session(
  *,
  asof: str,
  trades: list[dict[str, Any]],
  session_return_pct: float | None = None,
  strategy_id: str | None = None,
  ticker_cooldown_sessions: int = DEFAULT_TICKER_COOLDOWN_SESSIONS,
  entity_cooldown_sessions: int = DEFAULT_ENTITY_COOLDOWN_SESSIONS,
) -> dict[str, Any]:
  """Analyze day's trades and write/refresh anti-repeat rules."""
  st = seed_standing_policies(load_rules_ledger())
  trades = list(trades or [])
  sl_trades = [t for t in trades if str(t.get("exit_reason") or t.get("exit") or "") == "stop_loss"]
  loss_trades = [t for t in trades if float(t.get("pnl") or 0) < 0]
  win_trades = [t for t in trades if float(t.get("pnl") or 0) > 0]

  created: list[str] = []

  for t in sl_trades:
    tk = str(t.get("ticker") or "").upper().strip()
    if not tk:
      continue
    exp = _session_dates_after(asof, max(1, int(ticker_cooldown_sessions)))
    rid = f"exclude_ticker::{tk}"
    rule = {
      "id": rid,
      "kind": "exclude_ticker",
      "ticker": tk,
      "title": f"Do not re-buy {tk} after SL",
      "reason": (
        f"Stop-loss on {asof}: pnl={t.get('pnl')} ({t.get('pnl_pct')}%). "
        f"Cooldown-out {ticker_cooldown_sessions} session(s) through {exp}."
      ),
      "source_asof": asof,
      "expires_on": exp,
      "status": "active",
      "permanent": False,
      "strategy_id": strategy_id,
      "evidence": {
        "pnl": t.get("pnl"),
        "pnl_pct": t.get("pnl_pct"),
        "exit_reason": t.get("exit_reason") or t.get("exit"),
        "leverage": t.get("leverage") or t.get("lev"),
        "entity": t.get("bulk_entity") or t.get("entity_normalized"),
      },
    }
    _upsert_rule(st, rule)
    created.append(rid)

    ent = str(t.get("bulk_entity") or t.get("entity_normalized") or "").strip()
    if ent and entity_cooldown_sessions > 0:
      exp_e = _session_dates_after(asof, max(1, int(entity_cooldown_sessions)))
      eid = f"exclude_entity::{ent.upper()}"
      _upsert_rule(
        st,
        {
          "id": eid,
          "kind": "exclude_entity",
          "entity": ent,
          "title": f"Cool entity {ent[:48]}",
          "reason": (
            f"Entity behind SL on {tk} ({asof}). "
            f"Skip this discloser for {entity_cooldown_sessions} session(s)."
          ),
          "source_asof": asof,
          "expires_on": exp_e,
          "status": "active",
          "permanent": False,
          "strategy_id": strategy_id,
          "evidence": {"ticker": tk, "pnl": t.get("pnl")},
        },
      )
      created.append(eid)

  # Soft lessons from close-red (not SL): shorter ticker caution
  for t in loss_trades:
    if str(t.get("exit_reason") or t.get("exit") or "") == "stop_loss":
      continue
    tk = str(t.get("ticker") or "").upper().strip()
    if not tk:
      continue
    exp = _session_dates_after(asof, 1)
    rid = f"caution_ticker::{tk}"
    _upsert_rule(
      st,
      {
        "id": rid,
        "kind": "exclude_ticker",
        "ticker": tk,
        "title": f"Caution: {tk} closed red",
        "reason": (
          f"Held-to-close loss on {asof}: pnl={t.get('pnl')}. "
          f"Skip same name next session."
        ),
        "source_asof": asof,
        "expires_on": exp,
        "status": "active",
        "permanent": False,
        "strategy_id": strategy_id,
        "evidence": {"pnl": t.get("pnl"), "exit": t.get("exit_reason") or t.get("exit")},
      },
    )
    created.append(rid)

  # Streak → sit-out rule (only after a traded SL day — never re-arm on flat/sitout days)
  streak = dict(st.get("streak") or {})
  if sl_trades:
    if streak.get("last_asof") != asof:
      streak["sl_days"] = int(streak.get("sl_days") or 0) + 1
      streak["last_asof"] = asof
  elif trades:
    # Any traded session without SL breaks the streak
    streak["sl_days"] = 0
    streak["last_asof"] = asof
  # Empty session (sit-out / no fills): leave streak count but do not extend sitout
  st["streak"] = streak

  if sl_trades and int(streak.get("sl_days") or 0) >= CONSECUTIVE_SL_SITOUT:
    exp = _session_dates_after(asof, 1)
    _upsert_rule(
      st,
      {
        "id": "sitout_after_sl_streak",
        "kind": "sitout_session",
        "title": "Sit out next session after SL streak",
        "reason": (
          f"{streak['sl_days']} consecutive SL session(s) ending {asof}. "
          f"Flat book on next session through {exp}."
        ),
        "source_asof": asof,
        "expires_on": exp,
        "status": "active",
        "permanent": False,
        "strategy_id": strategy_id,
      },
    )
    created.append("sitout_after_sl_streak")

  # Positive reinforcement note (non-blocking)
  for t in win_trades:
    tk = str(t.get("ticker") or "")
    if not tk:
      continue
    _append_history(
      {
        "event": "win_noted",
        "asof": asof,
        "ticker": tk,
        "pnl": t.get("pnl"),
        "strategy_id": strategy_id,
      }
    )

  st["last_learned_asof"] = asof
  st["stats"]["learned_sessions"] = int(st["stats"].get("learned_sessions") or 0) + 1
  save_rules_ledger(st)
  _append_history(
    {
      "event": "learned",
      "asof": asof,
      "strategy_id": strategy_id,
      "session_return_pct": session_return_pct,
      "n_trades": len(trades),
      "n_sl": len(sl_trades),
      "n_loss": len(loss_trades),
      "rules_touched": sorted(set(created)),
    }
  )
  return {
    "asof": asof,
    "rules_touched": sorted(set(created)),
    "active_count": len(active_rules(asof, st)),
    "streak": streak,
    "ledger_path": str(RULES_PATH),
  }


def read_daily_briefing(asof: str, *, mark_read: bool = True) -> dict[str, Any]:
  """Mandatory pre-session read: active rules + excludes to apply today."""
  st = seed_standing_policies(load_rules_ledger())
  rules = active_rules(asof, st)
  exclude_tickers: list[str] = []
  exclude_entities: list[str] = []
  sitout = False
  lines: list[str] = []

  for r in rules:
    kind = str(r.get("kind") or "")
    title = str(r.get("title") or r.get("id"))
    reason = str(r.get("reason") or "")
    lines.append(f"• [{kind}] {title} — {reason}")
    if kind == "exclude_ticker" and r.get("ticker"):
      exclude_tickers.append(str(r["ticker"]).upper())
    elif kind == "exclude_entity" and r.get("entity"):
      exclude_entities.append(str(r["entity"]))
    elif kind == "sitout_session":
      sitout = True

  # Dedupe
  exclude_tickers = sorted(set(exclude_tickers))
  exclude_entities = sorted(set(exclude_entities))

  summary = (
    f"Rules briefing for {asof}: {len(rules)} active "
    f"({len(exclude_tickers)} tickers blocked, {len(exclude_entities)} entities blocked"
    f"{', SIT OUT' if sitout else ''})."
  )
  if not rules:
    summary = f"Rules briefing for {asof}: no active tactical rules (standing policies only)."

  if mark_read:
    st["last_briefing_asof"] = asof
    st["last_briefing_at"] = _now()
    st["stats"]["rules_fired"] = int(st["stats"].get("rules_fired") or 0) + len(
      [r for r in rules if r.get("kind") != "policy"]
    )
    save_rules_ledger(st)
    _append_history(
      {
        "event": "briefing_read",
        "asof": asof,
        "n_rules": len(rules),
        "exclude_tickers": exclude_tickers,
        "exclude_entities": exclude_entities,
        "sitout": sitout,
      }
    )

  return {
    "asof": asof,
    "summary": summary,
    "lines": lines,
    "rules": rules,
    "exclude_tickers": exclude_tickers,
    "exclude_entities": exclude_entities,
    "sitout": sitout,
    "last_learned_asof": st.get("last_learned_asof"),
    "read_at": st.get("last_briefing_at"),
    "ledger_path": str(RULES_PATH),
  }


def merge_excludes(
  briefing: dict[str, Any],
  *,
  exclude_tickers: list[str] | None = None,
  exclude_entities: list[str] | None = None,
) -> tuple[list[str], list[str], bool]:
  """Combine briefing blocks with any caller excludes."""
  tks = set(x.upper() for x in (exclude_tickers or []) if x)
  ents = set(x for x in (exclude_entities or []) if x)
  for x in briefing.get("exclude_tickers") or []:
    tks.add(str(x).upper())
  for x in briefing.get("exclude_entities") or []:
    ents.add(str(x))
  return sorted(tks), sorted(ents), bool(briefing.get("sitout"))
