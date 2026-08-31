"""Rules ledger — mine durable DO/DON'T rules from daily P&L; read before every session.

No LLM on the fire path. Rules are deterministic pattern extracts from fills + context.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from processor.hybrid.recognition.types import AgentMessage

ROOT = Path(__file__).resolve().parents[4]
LEDGER_PATH = ROOT / "models" / "godfather_rules_ledger.jsonl"
BRIEFING_PATH = ROOT / "models" / "godfather_daily_briefing.json"

MAX_ACTIVE_RULES = 40


def _now() -> str:
  return datetime.now(timezone.utc).isoformat()


def _rule_id(kind: str, key: str) -> str:
  h = hashlib.sha1(f"{kind}:{key}".encode()).hexdigest()[:8]
  return f"R-{kind}-{h}"


def load_ledger_rows(path: Path | None = None) -> list[dict[str, Any]]:
  p = path or LEDGER_PATH
  if not p.exists():
    return []
  rows: list[dict[str, Any]] = []
  for line in p.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
      continue
    try:
      rows.append(json.loads(line))
    except json.JSONDecodeError:
      continue
  return rows


def append_ledger(rule: dict[str, Any], path: Path | None = None) -> None:
  p = path or LEDGER_PATH
  p.parent.mkdir(parents=True, exist_ok=True)
  with p.open("a", encoding="utf-8") as f:
    f.write(json.dumps(rule, ensure_ascii=False) + "\n")


def _upsert_rule(rules: list[dict[str, Any]], rule: dict[str, Any]) -> list[dict[str, Any]]:
  rid = rule["id"]
  out: list[dict[str, Any]] = []
  found = False
  for r in rules:
    if r.get("id") == rid:
      merged = dict(r)
      merged["hits"] = int(r.get("hits") or 0) + 1
      merged["last_seen"] = rule.get("last_seen") or _now()
      ev = list(merged.get("evidence") or [])
      for e in rule.get("evidence") or []:
        ev.append(e)
      merged["evidence"] = ev[-8:]
      merged["active"] = True
      if rule.get("severity") == "hard":
        merged["severity"] = "hard"
      out.append(merged)
      found = True
    else:
      out.append(r)
  if not found:
    out.append(rule)
  # Prefer hard + high hits; drop oldest soft if over cap
  out.sort(key=lambda r: (0 if r.get("severity") == "hard" else 1, -int(r.get("hits") or 0)))
  return out[:MAX_ACTIVE_RULES]


def mine_rules_from_day(
  *,
  asof: str,
  traded: bool,
  pnl: float,
  trades: list[dict[str, Any]] | None,
  messages: list[dict[str, Any]] | None,
  regime_label: str | None,
  skip_reason: str | None,
) -> list[dict[str, Any]]:
  """Extract 0..N candidate rules from one session's P&L."""
  mined: list[dict[str, Any]] = []
  msgs = list(messages or [])
  fills = list(trades or [])
  ts = _now()

  if traded and pnl < 0 and fills:
    for t in fills:
      ticker = str(t.get("ticker") or "?")
      exit_reason = str(t.get("exit_reason") or "unknown")
      t_pnl = float(t.get("pnl") or 0)

      if exit_reason == "stop_loss":
        mined.append(
          {
            "id": _rule_id("exit", "stop_loss_asymmetric"),
            "kind": "exit_pattern",
            "rule": "Never let winners drip to session_close while losers full-stop — require take-profit path before next ORB fire.",
            "trigger": {"field": "exit_reason", "equals": "stop_loss"},
            "action": "require_tp",
            "severity": "soft",
            "hits": 1,
            "active": True,
            "created_at": ts,
            "last_seen": ts,
            "evidence": [{"asof": asof, "ticker": ticker, "pnl": t_pnl, "exit_reason": exit_reason}],
          }
        )
        mined.append(
          {
            "id": _rule_id("ticker_sl", ticker),
            "kind": "ticker_cooldown",
            "rule": f"Cooldown {ticker} after a stop_loss until two clean sessions pass without a re-hit on that name.",
            "trigger": {"field": "ticker", "equals": ticker},
            "action": "skip",
            "severity": "hard",
            "hits": 1,
            "active": True,
            "created_at": ts,
            "last_seen": ts,
            "cooldown_sessions": 1,
            "evidence": [{"asof": asof, "ticker": ticker, "pnl": t_pnl, "exit_reason": exit_reason}],
          }
        )

      if t_pnl < 0 and exit_reason == "session_close":
        mined.append(
          {
            "id": _rule_id("exit", "session_close_red"),
            "kind": "exit_pattern",
            "rule": "Session-close red = weak ORB; raise agreement τ and skip borderline MetaLabel takes next day.",
            "trigger": {"field": "exit_reason", "equals": "session_close"},
            "action": "raise_tau",
            "severity": "soft",
            "hits": 1,
            "active": True,
            "created_at": ts,
            "last_seen": ts,
            "evidence": [{"asof": asof, "ticker": ticker, "pnl": t_pnl}],
          }
        )

    if regime_label in ("chop", "risk_off"):
      mined.append(
        {
          "id": _rule_id("regime", regime_label),
          "kind": "regime_ban",
          "rule": f"Prefer cash when Regime={regime_label} — prior fills lost money in this label (soft).",
          "trigger": {"field": "regime", "equals": regime_label},
          "action": "skip",
          "severity": "soft",  # hard regime bans froze entire months
          "hits": 1,
          "active": True,
          "created_at": ts,
          "last_seen": ts,
          "evidence": [{"asof": asof, "pnl": pnl, "regime": regime_label}],
        }
      )

    # Agents that voted take on a losing day → soft distrust rule
    for m in msgs:
      if m.get("vote") != "take":
        continue
      agent = str(m.get("agent") or "")
      if agent in ("Cost",):  # Cost take is structural, not a mistake signal alone
        continue
      if not agent:
        continue
      mined.append(
        {
          "id": _rule_id("agent_false_take", agent),
          "kind": "agent_lesson",
          "rule": f"{agent} voted TAKE on a losing day — down-weight until it earns correct takes again.",
          "trigger": {"field": "agent", "equals": agent, "vote": "take"},
          "action": "down_weight",
          "severity": "soft",
          "hits": 1,
          "active": True,
          "created_at": ts,
          "last_seen": ts,
          "evidence": [{"asof": asof, "pnl": pnl, "agent": agent}],
        }
      )

  if traded and pnl > 0 and fills:
    for t in fills:
      if str(t.get("exit_reason")) == "take_profit":
        mined.append(
          {
            "id": _rule_id("exit", "tp_works"),
            "kind": "exit_pattern",
            "rule": "Take-profit exits paid — keep allow_take_profit on; do not revert to protect-only session_close.",
            "trigger": {"field": "policy", "equals": "allow_take_profit"},
            "action": "keep_tp",
            "severity": "soft",
            "hits": 1,
            "active": True,
            "created_at": ts,
            "last_seen": ts,
            "evidence": [{"asof": asof, "ticker": t.get("ticker"), "pnl": t.get("pnl")}],
          }
        )

  if not traded and skip_reason:
    mined.append(
      {
        "id": _rule_id("skip_ok", str(skip_reason)[:48]),
        "kind": "skip_reinforce",
        "rule": f"Cash day was intentional ({skip_reason}) — preserve selective gate; do not loosen MetaLabel hard veto from chat alone.",
        "trigger": {"field": "skip_pattern", "equals": str(skip_reason)[:64]},
        "action": "keep_selective",
        "severity": "soft",
        "hits": 1,
        "active": True,
        "created_at": ts,
        "last_seen": ts,
        "evidence": [{"asof": asof, "skip_reason": skip_reason}],
      }
    )

  return mined


def merge_mined_into_state(state: dict[str, Any], mined: list[dict[str, Any]]) -> dict[str, Any]:
  rules = list(state.get("rules") or [])
  for rule in mined:
    before = {r.get("id") for r in rules}
    rules = _upsert_rule(rules, rule)
    # Append to durable jsonl when new or when hits just incremented
    append_ledger({**rule, "event": "upsert", "ts": _now()})
    if rule["id"] not in before:
      pass  # already appended
  state["rules"] = rules
  state["n_rules"] = len(rules)
  state["n_hard_rules"] = sum(1 for r in rules if r.get("severity") == "hard" and r.get("active"))
  return state


def daily_briefing(state: dict[str, Any], *, asof: str | None = None) -> dict[str, Any]:
  """Mandatory pre-market read — active rules sorted hard-first."""
  rules = [r for r in (state.get("rules") or []) if r.get("active")]
  hard = [r for r in rules if r.get("severity") == "hard"]
  soft = [r for r in rules if r.get("severity") != "hard"]
  hard.sort(key=lambda r: -int(r.get("hits") or 0))
  soft.sort(key=lambda r: -int(r.get("hits") or 0))
  briefing = {
    "asof": asof or datetime.now(timezone.utc).date().isoformat(),
    "project": "godfather",
    "must_read_before_trade": True,
    "hard_rules": [
      {
        "id": r["id"],
        "rule": r.get("rule"),
        "action": r.get("action"),
        "hits": r.get("hits"),
        "trigger": r.get("trigger"),
        "last_seen": r.get("last_seen"),
      }
      for r in hard
    ],
    "soft_rules": [
      {
        "id": r["id"],
        "rule": r.get("rule"),
        "action": r.get("action"),
        "hits": r.get("hits"),
        "trigger": r.get("trigger"),
      }
      for r in soft[:12]
    ],
    "summary": (
      f"{len(hard)} hard / {len(soft)} soft rules active. "
      "Read hard rules before any session fire — same mistakes stay banned."
    ),
  }
  try:
    BRIEFING_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRIEFING_PATH.write_text(json.dumps(briefing, indent=2), encoding="utf-8")
  except OSError:
    pass
  return briefing


def match_rules(
  rules: list[dict[str, Any]],
  *,
  regime_label: str | None,
  candidate_ticker: str | None,
  asof: str | None = None,
  recent_tickers_with_sl: set[str] | None = None,
) -> list[dict[str, Any]]:
  """Return rules that apply to today's context (pre-trade)."""
  matched: list[dict[str, Any]] = []
  sl_set = recent_tickers_with_sl or set()
  asof_d = None
  if asof:
    try:
      asof_d = date.fromisoformat(asof[:10])
    except ValueError:
      asof_d = None

  for r in rules:
    if not r.get("active"):
      continue
    trig = r.get("trigger") or {}
    field = trig.get("field")
    equals = trig.get("equals")
    if field == "regime" and regime_label and equals == regime_label:
      matched.append(r)
    elif field == "ticker" and candidate_ticker and equals == candidate_ticker:
      # Expire ticker cooldown after N calendar days
      cool = int(r.get("cooldown_sessions") or 1)
      ev = r.get("evidence") or []
      last_asof = (ev[-1] or {}).get("asof") if ev else None
      expired = False
      if asof_d and last_asof:
        try:
          last_d = date.fromisoformat(str(last_asof)[:10])
          # ~1.5 calendar days per session (weekends)
          expired = (asof_d - last_d).days > max(1, cool) * 2
        except ValueError:
          expired = False
      if not expired:
        matched.append(r)
    elif field == "ticker" and candidate_ticker and candidate_ticker in sl_set and r.get("kind") == "ticker_cooldown":
      if equals == candidate_ticker:
        matched.append(r)
    elif field == "policy" and equals == "allow_take_profit":
      matched.append(r)
  return matched


def recent_sl_tickers(state: dict[str, Any], *, lookback: int = 5) -> set[str]:
  out: set[str] = set()
  for r in state.get("rules") or []:
    if r.get("kind") != "ticker_cooldown" or not r.get("active"):
      continue
    # still in cooldown if hits recent and cooldown not expired via evidence count
    trig = r.get("trigger") or {}
    tk = trig.get("equals")
    if tk:
      out.add(str(tk))
  # Also scan recent outcomes evidence in rules
  _ = lookback
  return out


def rules_clerk_message(
  state: dict[str, Any],
  *,
  asof: str,
  regime_label: str | None,
  candidate_ticker: str | None,
) -> tuple[AgentMessage, dict[str, Any]]:
  """Pre-trade clerk: reads ledger, hard-skip if a ban matches."""
  briefing = daily_briefing(state, asof=asof)
  matched = match_rules(
    list(state.get("rules") or []),
    regime_label=regime_label,
    candidate_ticker=candidate_ticker,
    asof=asof,
    recent_tickers_with_sl=recent_sl_tickers(state),
  )
  hard_hits = [
    r
    for r in matched
    if r.get("severity") == "hard"
    and r.get("action") == "skip"
    and r.get("kind") == "ticker_cooldown"  # only ticker cooldowns hard-block
  ]
  if hard_hits:
    ids = [r["id"] for r in hard_hits]
    msg = AgentMessage(
      agent="RulesClerk",
      vote="skip",
      weight=2.0,
      reason=f"ledger_ban|{','.join(ids[:3])}",
      payload={
        "hard": True,
        "matched_ids": ids,
        "rules": [r.get("rule") for r in hard_hits[:3]],
        "briefing_summary": briefing.get("summary"),
      },
      status="ok",
    )
    return msg, briefing

  soft_hits = [r for r in matched if r.get("severity") != "hard"]
  if soft_hits or briefing.get("hard_rules"):
    msg = AgentMessage(
      agent="RulesClerk",
      vote="annotate",
      weight=1.2,
      reason="briefing_read",
      payload={
        "hard": False,
        "n_hard_active": len(briefing.get("hard_rules") or []),
        "n_soft_matched": len(soft_hits),
        "top_rules": [r.get("rule") for r in (briefing.get("hard_rules") or [])[:3]],
        "briefing_summary": briefing.get("summary"),
      },
      status="ok",
    )
    return msg, briefing

  msg = AgentMessage(
    agent="RulesClerk",
    vote="annotate",
    reason="ledger_empty",
    payload={"hard": False, "briefing_summary": briefing.get("summary")},
    status="cold_start" if not (state.get("rules") or []) else "ok",
  )
  return msg, briefing
