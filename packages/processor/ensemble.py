"""Weighted ensemble + adaptive_edge playbook router (85% gate)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models import StrategyCandidate
from processor.adaptive_edge import adaptive_edge_for_ticker, feature_bin, load_state, load_ticker_profile
from processor.sentiment import mention_heat
from processor.strategies import intraday_orb, market_regime, mean_rev_bb, mom_cross
from processor.strategy_audit import CANDIDATES, load_playbook


DEFAULT_WEIGHTS = {
  "bulk_ml": 0.35,
  "adaptive_edge": 0.45,
  "mom_cross": 0.10,
  "mean_rev_bb": 0.10,
  "intraday_orb": 0.10,
  "trend_follow": 0.15,
  "mean_rev_chop": 0.10,
}

PLAYBOOK_FIRE_CONF = 0.70
LEGACY_FIRE_CONF = 0.62


def _live_enabled(db: Session) -> set[str]:
  rows = db.query(StrategyCandidate).filter(StrategyCandidate.live_enabled.is_(True)).all()
  if not rows:
    return {"bulk_ml", "adaptive_edge"}
  return {r.id for r in rows}


def seed_strategy_candidates(db: Session | None = None) -> int:
  own = db is None
  if own:
    db = SessionLocal()
  seeds = [
    ("bulk_ml", "ml", True, "LightGBM bulk scorer"),
    ("adaptive_edge", "adaptive", True, "Expanding-window 85% conditional hit gate"),
    ("macro_theme", "macro", False, "Theme filter / context"),
    ("mom_cross", "momentum", False, "MA cross — off shelf, playbook/adaptive gated"),
    ("mean_rev_bb", "mean_reversion", False, "Bollinger — off shelf"),
    ("trend_follow", "momentum", False, "Mom in trend only"),
    ("mean_rev_chop", "mean_reversion", False, "BB in chop only"),
    ("sent_filter", "sentiment", False, "Mention heat veto only"),
    ("intraday_orb", "intraday", False, "ORB needs session bars"),
  ]
  n = 0
  try:
    for sid, family, live, notes in seeds:
      row = db.query(StrategyCandidate).filter(StrategyCandidate.id == sid).first()
      if row is None:
        db.add(
          StrategyCandidate(
            id=sid,
            family=family,
            status="passed" if live else "candidate",
            live_enabled=live,
            notes=notes,
          )
        )
        n += 1
      else:
        if sid == "adaptive_edge" and not row.live_enabled:
          row.live_enabled = True
          row.status = "passed"
          row.notes = notes
          n += 1
        if sid == "mom_cross" and row.live_enabled:
          row.live_enabled = False
          row.notes = notes
          n += 1
    db.commit()
    return n
  finally:
    if own:
      db.close()


def _adaptive_decision(
  closes: list[float],
  *,
  ticker: str,
  bulk_prob: float | None,
) -> dict:
  regime = market_regime(closes) if closes else "unknown"
  if regime == "risk_off":
    return {
      "fire": False,
      "reason": "risk_off",
      "regime": regime,
      "confidence": 0.0,
      "strategy_id": "adaptive_edge",
    }
  if not closes:
    return {"fire": False, "reason": "no_closes", "confidence": 0.0, "strategy_id": "adaptive_edge"}

  st = load_state()
  profile = load_ticker_profile(ticker)
  sig = adaptive_edge_for_ticker(closes, ticker, buy_only=True)
  conf = float(sig.confidence)
  if bulk_prob is not None and sig.side == "buy":
    conf = 0.75 * conf + 0.25 * float(bulk_prob)

  fire = sig.side == "buy" and conf >= PLAYBOOK_FIRE_CONF and "gate_ok" in (sig.reason or "")
  return {
    "fire": fire,
    "reason": "ok" if fire else (sig.reason or "adaptive_flat"),
    "confidence": round(conf, 4),
    "strategy_id": "adaptive_edge",
    "book": "swing",
    "regime": regime,
    "side": sig.side,
    "bin": feature_bin(closes),
    "ticker_eligible": bool(profile and profile.get("ambition_pass")),
    "adaptive": {
      "effective_target": profile.get("effective_target") if profile else st.effective_target,
      "min_peers": profile.get("min_peers") if profile else st.min_peers,
      "tp": profile.get("tp") if profile else st.tp,
      "sl": profile.get("sl") if profile else st.sl,
      "rolling_hit": st.rolling_hit_rate(),
      "target_hit": st.target_hit,
    },
    "signal_reason": sig.reason,
  }


def decide_entry(
  closes: list[float],
  *,
  bulk_prob: float | None,
  ticker: str,
  db: Session | None = None,
) -> dict:
  own = db is None
  if own:
    db = SessionLocal()
  try:
    regime = market_regime(closes) if closes else "unknown"
    heat = mention_heat(ticker, db=db)
    if heat.get("veto"):
      return {"fire": False, "reason": "sentiment_veto", "regime": regime, "heat": heat}
    if regime == "risk_off":
      return {"fire": False, "reason": "risk_off", "regime": regime, "heat": heat}

    enabled = _live_enabled(db)
    if "adaptive_edge" in enabled:
      dec = _adaptive_decision(closes, ticker=ticker, bulk_prob=bulk_prob)
      dec["heat"] = heat
      return dec

    # Fallback: legacy playbook soft router (paper)
    pb = load_playbook(ticker)
    if pb and pb.get("status") == "passed" and pb.get("strategy_id") in CANDIDATES:
      fn = CANDIDATES[pb["strategy_id"]]
      s1 = fn(closes) if closes else None
      if s1 and s1.side == "buy" and pb.get("ambition_pass"):
        conf = float(s1.confidence)
        if bulk_prob is not None:
          conf = 0.7 * conf + 0.3 * float(bulk_prob)
        return {
          "fire": conf >= PLAYBOOK_FIRE_CONF,
          "reason": "playbook" if conf >= PLAYBOOK_FIRE_CONF else "conf_low",
          "confidence": round(conf, 4),
          "strategy_id": pb["strategy_id"],
          "book": "swing",
          "regime": regime,
          "heat": heat,
        }

    votes: list[tuple[str, float, str]] = []
    if "bulk_ml" in enabled and bulk_prob is not None:
      votes.append(("bulk_ml", float(bulk_prob), "swing"))
    if closes and "mom_cross" in enabled:
      s = mom_cross(closes)
      if s.side == "buy":
        votes.append(("mom_cross", s.confidence, "swing"))
    if closes and "mean_rev_bb" in enabled and regime == "chop":
      s = mean_rev_bb(closes)
      if s.side == "buy":
        votes.append(("mean_rev_bb", s.confidence, "swing"))
    if closes and "intraday_orb" in enabled:
      s = intraday_orb(closes)
      if s.side == "buy":
        votes.append(("intraday_orb", s.confidence, "day"))

    if not votes:
      return {"fire": False, "reason": "no_votes", "regime": regime, "heat": heat}

    num = den = 0.0
    best = votes[0]
    for sid, conf, book in votes:
      w = DEFAULT_WEIGHTS.get(sid, 0.1)
      num += w * conf
      den += w
      if conf > best[1]:
        best = (sid, conf, book)
    conf = num / den if den else best[1]
    conf = min(0.95, conf + 0.03 * float(heat.get("heat") or 0))
    return {
      "fire": conf >= LEGACY_FIRE_CONF,
      "confidence": round(conf, 4),
      "strategy_id": best[0] if len(votes) == 1 else "ensemble",
      "book": best[2],
      "votes": [{"id": a, "conf": b, "book": c} for a, b, c in votes],
      "regime": regime,
      "heat": heat,
      "reason": "legacy_ensemble",
    }
  finally:
    if own:
      db.close()
