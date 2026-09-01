"""Pattern Forge v2 mistake ledger — learn after the day closes; ban repeats next open.

Flow (daily_swing product path):
  1. End of day T (exit known at T+1 close) → learn_from_day() writes rules + mistake rows.
  2. Morning of day U → read_briefing(U) loads active bans / size-downs / sit-outs.
  3. choose_daily_candidate must honor exclude_tickers + sitout + size_mult (never amplify).

No LLM on the fire path. Paper/sim learning only until a live gate exists.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from processor.pattern_forge.adaptive_learn import (
  FP_EXPIRE_SESSIONS,
  MIN_DAY_RET_FOR_FP,
  context_fingerprint,
  fingerprint_rule_from_failure,
  match_fingerprint_rules,
)

ROOT = Path(__file__).resolve().parents[3]
LEDGER_DIR = ROOT / "models" / "pattern_forge"
RULES_PATH = LEDGER_DIR / "mistake_rules.json"
MISTAKES_PATH = LEDGER_DIR / "mistakes.jsonl"
HISTORY_PATH = LEDGER_DIR / "mistake_history.jsonl"

DEFAULT_TICKER_COOLDOWN = 3  # sessions after a meaningful loss
DEFAULT_BIG_LOSS_COOLDOWN = 5  # sessions after pnl_pct ≤ −2%
RED_DAY_SIZE_MULT = 0.75  # soft — hard 0.5 over-sat and killed greens
CONSECUTIVE_RED_SITOUT = 3  # was 2; too trigger-happy on FO noise
MIN_LOSS_PCT_TO_BAN = -0.4  # ignore tiny −0.1% fee noise as "mistakes"
MIN_DAY_RET_FOR_STREAK = -0.6  # day_return_pct units (%); ignore tiny reds for sitout streak


def _now() -> str:
  return datetime.now(timezone.utc).isoformat()


def _empty() -> dict[str, Any]:
  return {
    "version": 1,
    "lane": "pattern_forge_v2",
    "updated_at": None,
    "last_learned_asof": None,
    "last_briefing_asof": None,
    "rules": [],
    "streak": {"red_days": 0, "last_asof": None},
    "stats": {
      "learned_days": 0,
      "mistakes_logged": 0,
      "rules_created": 0,
      "repeats_blocked": 0,
    },
  }


def load_rules() -> dict[str, Any]:
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
  base.setdefault("streak", {"red_days": 0, "last_asof": None})
  base.setdefault("stats", _empty()["stats"])
  return base


def save_rules(state: dict[str, Any]) -> None:
  import time
  import uuid

  LEDGER_DIR.mkdir(parents=True, exist_ok=True)
  state = dict(state)
  state["updated_at"] = _now()
  payload = json.dumps(state, indent=2, default=str)
  tmp = RULES_PATH.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
  tmp.write_text(payload, encoding="utf-8")
  last_err: Exception | None = None
  for attempt in range(8):
    try:
      tmp.replace(RULES_PATH)
      return
    except (PermissionError, OSError) as exc:
      last_err = exc
      time.sleep(0.05 * (attempt + 1))
      try:
        RULES_PATH.write_text(payload, encoding="utf-8")
        try:
          tmp.unlink(missing_ok=True)
        except OSError:
          pass
        return
      except (PermissionError, OSError) as exc2:
        last_err = exc2
        time.sleep(0.08 * (attempt + 1))
  try:
    tmp.unlink(missing_ok=True)
  except OSError:
    pass
  # Last resort: write sidecar so learning is not lost; bakeoff continues
  sidecar = RULES_PATH.with_suffix(".json.fallback")
  try:
    sidecar.write_text(payload, encoding="utf-8")
  except OSError:
    pass
  if last_err is not None:
    # Soft-fail for Windows file locks during parallel/long bakeoffs
    print(f"warning: mistake_rules save deferred ({last_err}); wrote {sidecar.name}", flush=True)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": _now(), **row}, default=str) + "\n")


def _session_dates_after(asof: str, n: int) -> str:
  d = date.fromisoformat(asof[:10])
  left = max(0, int(n))
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
  st = state or load_rules()
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
    rules.append({**rule, "hits": 1, "created_at": _now(), "updated_at": _now()})
    state["stats"]["rules_created"] = int(state["stats"].get("rules_created") or 0) + 1
  state["rules"] = rules


def seed_standing_policies(state: dict[str, Any] | None = None) -> dict[str, Any]:
  st = state or load_rules()
  policies = [
    {
      "id": "policy_product_lev_le_3",
      "kind": "policy",
      "title": "Product leverage ≤ 3",
      "reason": "Council lock: optimize worst-month at lev≤3; stretch lev is research-only.",
      "status": "active",
      "permanent": True,
    },
    {
      "id": "policy_no_session_orb",
      "kind": "policy",
      "title": "No session/5m ORB in product",
      "reason": "Costs > edge on 1h/5m ORB; FrequencyORB killed.",
      "status": "active",
      "permanent": True,
    },
    {
      "id": "policy_read_mistakes_before_fire",
      "kind": "policy",
      "title": "Read mistake ledger before every fire",
      "reason": "Same ticker / same red-day pattern must not auto-repeat.",
      "status": "active",
      "permanent": True,
    },
    {
      "id": "policy_agents_veto_only",
      "kind": "policy",
      "title": "Agents may only reduce risk",
      "reason": "Cross-market / breadth / similarity never amplify size.",
      "status": "active",
      "permanent": True,
    },
    # v5 → v2 lessons (freq + bad months). Applied when apply_standing_freq=True (v2.2).
    {
      "id": "policy_freq_ticker_cooldown_1",
      "kind": "frequency",
      "title": "1-session ticker cooldown after a trade",
      "reason": "v5_freq: cutting immediate re-fires reduced Oct bleed without killing 2025 (+99.5% vs v2 +103%).",
      "status": "active",
      "permanent": True,
      "ticker_cooldown_days": 1,
    },
    {
      "id": "policy_freq_loss_streak_sitout_3",
      "kind": "frequency",
      "title": "Sit one day after 3 meaningful reds",
      "reason": "v5_freq: loss_streak_sitout=3 improved several v2 crash months (e.g. 2021 Oct −20.8% → −4.3%).",
      "status": "active",
      "permanent": True,
      "loss_streak_sitout": 3,
    },
    {
      "id": "policy_freq_max_trades_month_16",
      "kind": "frequency",
      "title": "Cap ~16 trades/month",
      "reason": "v5_freq: month cap cuts churn in noisy months; keeps top_k=1 concentration edge.",
      "status": "active",
      "permanent": True,
      "max_trades_per_month": 16,
    },
    {
      "id": "policy_calendar_october_soft",
      "kind": "calendar_soft",
      "title": "October soft size ×0.5",
      "reason": "v2 multi-year: October is the worst calendar cluster (−28.9% 2024, −21.5% 2020, −20.8% 2021, −17.4% 2023). Soft size only — do not sit out (sit-out costs green Oct days).",
      "status": "active",
      "permanent": True,
      "months": ["october"],
      "size_mult": 0.5,
    },
    {
      "id": "policy_v23_asymmetric_attack",
      "kind": "policy",
      "title": "v2.3 asymmetric attack/defense",
      "reason": "Keep freq defenses only when underwater or market defense; when YTD green / prior month green, lift trade caps and fire full size to raise year-end. Oct soft only if underwater.",
      "status": "active",
      "permanent": True,
    },
    {
      "id": "policy_adaptive_fingerprint_learn",
      "kind": "policy",
      "title": "Learn failure contexts, not calendar months",
      "reason": "Forward path: fingerprint regime/breadth/underwater/streak after meaningful reds; require repeated evidence before size-down/sit. No July/October hardcodes as alpha.",
      "status": "active",
      "permanent": True,
    },
  ]
  changed = False
  existing = {str(r.get("id")): r for r in st["rules"]}
  for p in policies:
    rid = str(p["id"])
    if rid not in existing:
      _upsert_rule(st, p)
      changed = True
    else:
      # Refresh permanent policy text/params without bumping hits spam
      old = existing[rid]
      if old.get("permanent") and (
        old.get("reason") != p.get("reason")
        or old.get("ticker_cooldown_days") != p.get("ticker_cooldown_days")
        or old.get("loss_streak_sitout") != p.get("loss_streak_sitout")
        or old.get("max_trades_per_month") != p.get("max_trades_per_month")
        or old.get("months") != p.get("months")
        or old.get("size_mult") != p.get("size_mult")
      ):
        merged = {**old, **p, "hits": int(old.get("hits") or 1), "updated_at": _now()}
        for i, r in enumerate(st["rules"]):
          if str(r.get("id")) == rid:
            st["rules"][i] = merged
            break
        changed = True
  if changed:
    save_rules(st)
  return st


def standing_freq_knobs(state: dict[str, Any] | None = None) -> dict[str, Any]:
  """Merge active frequency + calendar_soft standing policies into runner knobs."""
  st = state or load_rules()
  out: dict[str, Any] = {}
  months: list[str] = []
  soft_mult = 1.0
  for r in st.get("rules") or []:
    if str(r.get("status") or "active") != "active":
      continue
    kind = str(r.get("kind") or "")
    if kind == "frequency":
      if r.get("ticker_cooldown_days") is not None:
        out["ticker_cooldown_days"] = max(
          int(out.get("ticker_cooldown_days") or 0), int(r["ticker_cooldown_days"])
        )
      if r.get("loss_streak_sitout") is not None:
        out["loss_streak_sitout"] = max(
          int(out.get("loss_streak_sitout") or 0), int(r["loss_streak_sitout"])
        )
      if r.get("max_trades_per_month") is not None:
        cur = int(out.get("max_trades_per_month") or 0)
        val = int(r["max_trades_per_month"])
        out["max_trades_per_month"] = min(cur, val) if cur > 0 else val
    elif kind == "calendar_soft":
      for m in r.get("months") or []:
        months.append(str(m).lower())
      try:
        soft_mult = min(soft_mult, float(r.get("size_mult") or 1.0))
      except (TypeError, ValueError):
        pass
  if months:
    out["calendar_soft_months"] = sorted(set(months))
    out["calendar_soft_mult"] = soft_mult if soft_mult < 1.0 else 0.5
  return out


def learn_from_day(
  *,
  asof: str,
  trades: list[dict[str, Any]],
  day_pnl: float | None = None,
  day_return_pct: float | None = None,
  regime: str | None = None,
  breadth_frac: float | None = None,
  breadth_stress: bool | None = None,
  ytd_underwater: bool = False,
  loss_streak: int = 0,
  market_mode: str | None = None,
  family: str = "daily_swing",
  ticker_cooldown: int = DEFAULT_TICKER_COOLDOWN,
  big_loss_cooldown: int = DEFAULT_BIG_LOSS_COOLDOWN,
  adaptive_fingerprints: bool = True,
) -> dict[str, Any]:
  """After exits for day `asof` are known — log mistakes and refresh anti-repeat rules."""
  st = seed_standing_policies(load_rules())
  trades = list(trades or [])
  losses = [t for t in trades if float(t.get("pnl") or 0) < 0]
  wins = [t for t in trades if float(t.get("pnl") or 0) > 0]
  touched: list[str] = []
  mistakes: list[dict[str, Any]] = []
  fp = context_fingerprint(
    regime=regime,
    breadth_frac=breadth_frac,
    breadth_stress=breadth_stress,
    ytd_underwater=ytd_underwater,
    loss_streak=loss_streak,
    market_mode=market_mode,
  )

  for t in losses:
    tk = str(t.get("ticker") or "").upper().strip()
    if not tk:
      continue
    pnl_pct = float(t.get("pnl_pct") or 0)
    if pnl_pct > MIN_LOSS_PCT_TO_BAN:
      # Fee/noise reds — log history only, do not ban
      _append_jsonl(
        HISTORY_PATH,
        {"event": "noise_loss_ignored", "asof": asof, "ticker": tk, "pnl_pct": pnl_pct},
      )
      continue
    cooldown = big_loss_cooldown if pnl_pct <= -2.0 else ticker_cooldown
    exp = _session_dates_after(asof, cooldown)
    rid = f"exclude_ticker::{tk}"
    mistake = {
      "kind": "mistake",
      "mistake_type": "losing_trade",
      "asof": asof,
      "ticker": tk,
      "family": family,
      "pnl": t.get("pnl"),
      "pnl_pct": t.get("pnl_pct"),
      "exit_reason": t.get("exit_reason"),
      "regime": regime,
      "breadth_frac": breadth_frac,
      "lesson": f"Do not re-buy {tk} for {cooldown} session(s) (through {exp}).",
      "rule_id": rid,
    }
    mistakes.append(mistake)
    _append_jsonl(MISTAKES_PATH, mistake)
    _upsert_rule(
      st,
      {
        "id": rid,
        "kind": "exclude_ticker",
        "ticker": tk,
        "title": f"Ban re-buy {tk} after loss",
        "reason": mistake["lesson"],
        "source_asof": asof,
        "expires_on": exp,
        "status": "active",
        "permanent": False,
        "family": family,
        "evidence": {
          "pnl": t.get("pnl"),
          "pnl_pct": t.get("pnl_pct"),
          "exit_reason": t.get("exit_reason"),
          "signal_reason": t.get("signal_reason"),
        },
      },
    )
    touched.append(rid)

    # Feature fingerprint: mild-momentum band chase that lost
    sig = str(t.get("signal_reason") or "")
    if "daily_swing" in sig and pnl_pct <= -1.5:
      frid = "caution_chase_band"
      _upsert_rule(
        st,
        {
          "id": frid,
          "kind": "size_down",
          "size_mult": 0.75,
          "title": "Size-down after chase-band losses",
          "reason": f"Lossy daily_swing chase on {asof} ({tk} {pnl_pct}%). Soft size 0.75 for 2 sessions.",
          "source_asof": asof,
          "expires_on": _session_dates_after(asof, 2),
          "status": "active",
          "permanent": False,
          "family": family,
        },
      )
      touched.append(frid)

  day_ret = float(day_return_pct) if day_return_pct is not None else None
  if day_ret is None and day_pnl is not None:
    # caller should pass day_return_pct; approximate only if missing
    day_ret = None
  day_meaningful_red = bool(day_ret is not None and day_ret <= MIN_DAY_RET_FOR_STREAK)
  if not day_meaningful_red and day_pnl is not None and day_ret is None:
    day_meaningful_red = float(day_pnl) < 0

  streak = dict(st.get("streak") or {})
  if trades and day_meaningful_red:
    if streak.get("last_asof") != asof:
      streak["red_days"] = int(streak.get("red_days") or 0) + 1
      streak["last_asof"] = asof
    mist = {
      "kind": "mistake",
      "mistake_type": "red_day",
      "asof": asof,
      "family": family,
      "day_pnl": day_pnl,
      "day_return_pct": day_return_pct,
      "n_losses": len(losses),
      "lesson": f"Red day {asof}: next session size×{RED_DAY_SIZE_MULT} (or sit if streak≥{CONSECUTIVE_RED_SITOUT}).",
      "rule_id": "size_after_red_day",
    }
    mistakes.append(mist)
    _append_jsonl(MISTAKES_PATH, mist)
    _upsert_rule(
      st,
      {
        "id": "size_after_red_day",
        "kind": "size_down",
        "size_mult": RED_DAY_SIZE_MULT,
        "title": "Soft size after meaningful red day",
        "reason": mist["lesson"],
        "source_asof": asof,
        "expires_on": _session_dates_after(asof, 1),
        "status": "active",
        "permanent": False,
        "family": family,
      },
    )
    touched.append("size_after_red_day")
  elif trades:
    streak["red_days"] = 0
    streak["last_asof"] = asof
  st["streak"] = streak

  if trades and day_meaningful_red and int(streak.get("red_days") or 0) >= CONSECUTIVE_RED_SITOUT:
    exp = _session_dates_after(asof, 1)
    rid = "sitout_after_red_streak"
    mist = {
      "kind": "mistake",
      "mistake_type": "red_streak_sitout",
      "asof": asof,
      "family": family,
      "red_days": streak["red_days"],
      "lesson": f"{streak['red_days']} consecutive red days ending {asof} → sit through {exp}.",
      "rule_id": rid,
    }
    mistakes.append(mist)
    _append_jsonl(MISTAKES_PATH, mist)
    _upsert_rule(
      st,
      {
        "id": rid,
        "kind": "sitout_session",
        "title": "Sit out after consecutive red days",
        "reason": mist["lesson"],
        "source_asof": asof,
        "expires_on": exp,
        "status": "active",
        "permanent": False,
        "family": family,
      },
    )
    touched.append(rid)

  for t in wins:
    _append_jsonl(
      HISTORY_PATH,
      {
        "event": "win_noted",
        "asof": asof,
        "ticker": t.get("ticker"),
        "pnl": t.get("pnl"),
        "family": family,
      },
    )


  # Adaptive fingerprints: learn failure *contexts* (not calendar months)
  if adaptive_fingerprints and trades and day_ret is not None and day_ret <= MIN_DAY_RET_FOR_FP:
    prior = 0
    for r in st.get("rules") or []:
      if str(r.get("id")) == fp["id"]:
        prior = int(r.get("evidence_hits") or 0)
        break
    exp = _session_dates_after(asof, FP_EXPIRE_SESSIONS)
    frule = fingerprint_rule_from_failure(
      fp=fp,
      asof=asof,
      day_return_pct=float(day_ret),
      expires_on=exp,
      prior_hits=prior,
    )
    # Replace-in-place without double-counting evidence_hits via _upsert_rule hits
    rules = list(st.get("rules") or [])
    found = False
    for i, r in enumerate(rules):
      if str(r.get("id")) == frule["id"]:
        rules[i] = {**r, **frule, "updated_at": _now()}
        found = True
        break
    if not found:
      rules.append({**frule, "hits": 1, "created_at": _now(), "updated_at": _now()})
      st["stats"]["rules_created"] = int(st["stats"].get("rules_created") or 0) + 1
    st["rules"] = rules
    touched.append(frule["id"])
    mist_fp = {
      "kind": "mistake",
      "mistake_type": "context_fingerprint",
      "asof": asof,
      "family": family,
      "day_return_pct": day_ret,
      "fingerprint": fp,
      "lesson": frule["reason"],
      "rule_id": frule["id"],
      "evidence_hits": frule["evidence_hits"],
      "active_defense": frule["active_defense"],
    }
    mistakes.append(mist_fp)
    _append_jsonl(MISTAKES_PATH, mist_fp)

  st["last_learned_asof"] = asof
  st["stats"]["learned_days"] = int(st["stats"].get("learned_days") or 0) + 1
  st["stats"]["mistakes_logged"] = int(st["stats"].get("mistakes_logged") or 0) + len(mistakes)
  save_rules(st)
  _append_jsonl(
    HISTORY_PATH,
    {
      "event": "learned",
      "asof": asof,
      "family": family,
      "day_pnl": day_pnl,
      "day_return_pct": day_return_pct,
      "n_trades": len(trades),
      "n_losses": len(losses),
      "rules_touched": sorted(set(touched)),
      "mistakes": len(mistakes),
      "fingerprint_id": fp.get("id"),
    },
  )
  return {
    "asof": asof,
    "rules_touched": sorted(set(touched)),
    "mistakes": mistakes,
    "active_count": len(active_rules(asof, st)),
    "streak": streak,
    "fingerprint": fp,
    "ledger_path": str(RULES_PATH),
    "mistakes_path": str(MISTAKES_PATH),
  }


def read_briefing(
  asof: str,
  *,
  mark_read: bool = True,
  regime: str | None = None,
  breadth_frac: float | None = None,
  breadth_stress: bool | None = None,
  ytd_underwater: bool = False,
  loss_streak: int = 0,
  market_mode: str | None = None,
  apply_fingerprints: bool = True,
) -> dict[str, Any]:
  """Pre-fire read: tickers banned, sit-out, and size multiplier (≤ 1)."""
  st = seed_standing_policies(load_rules())
  rules = active_rules(asof, st)
  exclude_tickers: list[str] = []
  sitout = False
  size_mult = 1.0
  lines: list[str] = []
  fp_match: dict[str, Any] = {}

  for r in rules:
    kind = str(r.get("kind") or "")
    title = str(r.get("title") or r.get("id"))
    reason = str(r.get("reason") or "")
    lines.append(f"• [{kind}] {title} — {reason}")
    if kind == "exclude_ticker" and r.get("ticker"):
      exclude_tickers.append(str(r["ticker"]).upper())
    elif kind == "sitout_session":
      sitout = True
    elif kind == "size_down":
      try:
        size_mult = min(size_mult, float(r.get("size_mult") or 1.0))
      except (TypeError, ValueError):
        pass

  if apply_fingerprints:
    fp = context_fingerprint(
      regime=regime,
      breadth_frac=breadth_frac,
      breadth_stress=breadth_stress,
      ytd_underwater=ytd_underwater,
      loss_streak=loss_streak,
      market_mode=market_mode,
    )
    fp_match = match_fingerprint_rules(rules, fp=fp)
    if fp_match.get("sitout"):
      sitout = True
    size_mult = min(size_mult, float(fp_match.get("size_mult") or 1.0))
    for m in fp_match.get("matched") or []:
      if m.get("applied"):
        lines.append(f"• [fingerprint] {m.get('title')} — {m.get('reason')}")

  exclude_tickers = sorted(set(exclude_tickers))
  size_mult = max(0.0, min(1.0, size_mult))

  summary = (
    f"Mistake briefing {asof}: {len(rules)} active "
    f"({len(exclude_tickers)} tickers banned"
    f"{', SIT OUT' if sitout else ''}"
    f"{f', size×{size_mult}' if size_mult < 1 else ''})."
  )
  if not any(r.get("kind") != "policy" for r in rules):
    summary = f"Mistake briefing {asof}: standing policies only — no tactical bans."

  if mark_read:
    st["last_briefing_asof"] = asof
    st["last_briefing_at"] = _now()
    save_rules(st)
    _append_jsonl(
      HISTORY_PATH,
      {
        "event": "briefing_read",
        "asof": asof,
        "n_rules": len(rules),
        "exclude_tickers": exclude_tickers,
        "sitout": sitout,
        "size_mult": size_mult,
      },
    )

  return {
    "asof": asof,
    "summary": summary,
    "lines": lines,
    "rules": rules,
    "exclude_tickers": exclude_tickers,
    "sitout": sitout,
    "size_mult": size_mult,
    "fingerprint": (fp_match or {}).get("fingerprint"),
    "fingerprint_match": fp_match,
    "last_learned_asof": st.get("last_learned_asof"),
    "stats": st.get("stats"),
    "ledger_path": str(RULES_PATH),
    "mistakes_path": str(MISTAKES_PATH),
  }


def note_repeat_blocked(*, asof: str, ticker: str, rule_id: str | None = None) -> None:
  st = load_rules()
  st["stats"]["repeats_blocked"] = int(st["stats"].get("repeats_blocked") or 0) + 1
  save_rules(st)
  _append_jsonl(
    HISTORY_PATH,
    {
      "event": "repeat_blocked",
      "asof": asof,
      "ticker": ticker,
      "rule_id": rule_id or f"exclude_ticker::{ticker.upper()}",
    },
  )


def reset_ledger(*, keep_mistake_log: bool = True) -> dict[str, Any]:
  """Clear tactical rules for a clean year/sim run (standing policies re-seeded)."""
  st = _empty()
  save_rules(st)
  seed_standing_policies()
  if not keep_mistake_log and MISTAKES_PATH.exists():
    MISTAKES_PATH.unlink()
  return load_rules()


def recent_mistakes(limit: int = 100) -> list[dict[str, Any]]:
  if not MISTAKES_PATH.exists():
    return []
  lines = MISTAKES_PATH.read_text(encoding="utf-8").strip().splitlines()
  out: list[dict[str, Any]] = []
  for line in lines[-limit:]:
    try:
      out.append(json.loads(line))
    except Exception:
      continue
  out.reverse()
  return out
