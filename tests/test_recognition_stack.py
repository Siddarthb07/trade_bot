"""Godfather recognition stack tests — synthetic, no network, no LLM."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.hybrid.recognition.detectors.hmm import filtered_at_t, filtered_regime
from processor.hybrid.recognition.ecology import assert_no_cross_softmax
from processor.hybrid.recognition.models.meta_label import score_take
from processor.hybrid.recognition.models.triple_barrier import first_barrier_touch
from processor.hybrid.recognition.stack import recognize_session
from processor.hybrid.recognition.stubs import hawkes_message, kyle_message, vpin_message
from processor.hybrid.recognition.swarm.similarity import DEFAULT_TEMPLATES, dtw_distance
from processor.hybrid.recognition.swarm.supervisor import collapse_skips, decide_agreement
from processor.hybrid.recognition.swarm.ticker_workers import map_tickers
from processor.hybrid.recognition.types import AgentMessage, SessionGeometry, RegimePosterior
from processor.hybrid.recognition.allocator import apply_size_overlays


def _trend_closes(n: int = 80) -> list[float]:
  return [100.0 * (1.01 ** i) for i in range(n)]


def _chop_closes(n: int = 80) -> list[float]:
  return [100.0 + (0.5 if i % 2 == 0 else -0.5) for i in range(n)]


def _bars_from_closes(closes: list[float]) -> list[dict]:
  out = []
  for c in closes:
    out.append({"open": c, "high": c * 1.002, "low": c * 0.998, "close": c, "volume": 1000})
  return out


def test_hmm_trend_vs_chop():
  t = filtered_regime(_trend_closes())
  c = filtered_regime(_chop_closes())
  assert t.status == "ok"
  assert t.label in ("trend", "chop", "risk_off")
  # trending path should not be risk_off
  assert t.p_risk_off <= c.p_risk_off + 0.5


def test_hmm_no_lookahead():
  closes = _trend_closes(60)
  a = filtered_at_t(closes, 40)
  closes2 = list(closes)
  closes2[-1] = closes2[-1] * 0.5  # future crash
  b = filtered_at_t(closes2, 40)
  assert a.p_trend == b.p_trend
  assert a.label == b.label


def test_triple_barrier_tp_first():
  entry = 100.0
  path = [100.2, 100.5, 101.2, 99.0]
  hit, i = first_barrier_touch(path, entry=entry, side="buy", tp_pct=0.01, sl_pct=0.02, max_bars=10)
  assert hit == "tp"
  assert i == 2


def test_meta_label_cannot_flip_side():
  geom = SessionGeometry(or_width_pct=0.01, status="ok")
  reg = RegimePosterior(label="trend", p_trend=0.8, status="ok")
  p, msg = score_take(primary_side="buy", geometry=geom, regime=reg)
  assert msg.payload["primary_side"] == "buy"
  p2, msg2 = score_take(primary_side=None, geometry=geom, regime=reg)
  assert p2 == 0.0
  assert msg2.vote == "skip"


def test_stubs_proxy_vote_on_bars():
  closes = _trend_closes(30)
  bars = _bars_from_closes(closes)
  # Give rising volume so proxies engage
  for i, b in enumerate(bars):
    b["volume"] = 1000 + i * 50
  v = vpin_message(bars)
  h = hawkes_message(ecology="nse", bars=bars)
  k = kyle_message(bars)
  assert v.status == "ok"
  assert h.status == "ok"
  assert k.status == "ok"
  assert v.vote in ("take", "skip", "annotate")
  assert "proxy" in (v.payload or {})


def test_stubs_insufficient_without_bars():
  assert vpin_message().status == "insufficient_data"
  assert kyle_message().status == "insufficient_data"
  assert hawkes_message(ecology="nse").status == "insufficient_data"


def test_correlated_skips_collapse():
  msgs = [
    AgentMessage(agent="Similarity", vote="skip"),
    AgentMessage(agent="LineGeometry", vote="skip"),
    AgentMessage(agent="Regime", vote="skip"),
    AgentMessage(agent="Cost", vote="skip"),
  ]
  raw, collapsed = collapse_skips(msgs)
  assert raw == 4
  assert collapsed == 2  # one correlated group + Cost


def test_ecology_blocks_meme_in_nse():
  with pytest.raises(ValueError):
    assert_no_cross_softmax("nse", ["momentum_attention"])


def test_ticker_workers_deterministic():
  def fn(t: str) -> dict:
    return {"ticker": t, "score": len(t)}

  a = map_tickers(["TCS.NS", "INFY.NS", "RELIANCE.NS"], fn)
  b = map_tickers(["RELIANCE.NS", "INFY.NS", "TCS.NS"], fn)
  assert [r["ticker"] for r in a] == [r["ticker"] for r in b]


def test_guards_cap_when_recognition_wants_size():
  lev, notes = apply_size_overlays(
    10.0,
    sl_frac=0.02,
    equity=10_000,
    cash_start=10_000,
    max_trade_risk_pct=2.0,
    max_daily_loss_pct=4.0,
    size_mult=1.0,
  )
  assert lev < 10.0
  assert any("cap" in n for n in notes)


def test_recognize_session_product_lane():
  closes = _trend_closes(40)
  bars = _bars_from_closes(closes[-24:])
  snap = recognize_session(
    asof="2026-08-26",
    bars=bars,
    daily_closes=closes,
    primary_side="buy",
    prev_close=closes[-25],
    tau=0.5,
    learn_state={"tau": 0.5, "meta_bias": 0.0, "agent_weights": {}, "n_outcome_updates": 0, "fleet_bias": 0.0, "recent_skip_rate": 0.5, "hit_rates": {}},
  )
  assert snap.project == "godfather"
  assert snap.ecology == "nse"
  assert snap.regime.label in ("trend", "chop", "risk_off", "unknown")
  agents = {m.agent for m in snap.messages}
  assert "Similarity" in agents
  assert "LineGeometry" in agents
  assert "MetaLabel" in agents
  assert "Changepoint" in agents
  assert "Hurst" in agents
  assert "JumpRisk" in agents
  assert "OutcomeLearner" in agents
  assert "VPIN" in agents
  # stubs should be voting proxies when bars present
  stub_status = {m.agent: m.status for m in snap.messages if m.agent in ("VPIN", "Hawkes", "Kyle")}
  assert stub_status.get("VPIN") == "ok"
  assert "LLM" not in agents
  assert len(agents) >= 18


def test_learn_loop_outcome_and_lesson(tmp_path):
  from processor.hybrid.recognition.learn import (
    apply_outcome,
    default_state,
    ingest_lesson,
    save_state,
    load_state,
  )

  path = tmp_path / "learn.json"
  st = default_state()
  st = apply_outcome(
    st,
    asof="2026-08-03",
    messages=[
      {"agent": "MetaLabel", "vote": "take"},
      {"agent": "Cost", "vote": "take"},
      {"agent": "Regime", "vote": "skip"},
    ],
    pnl=50.0,
    traded=True,
    trades=[{"ticker": "TCS.NS", "pnl": 50.0, "exit_reason": "take_profit"}],
    regime_label="trend",
  )
  assert st["n_outcome_updates"] == 1
  assert st["agent_weights"]["MetaLabel"] > 1.0
  st = ingest_lesson(st, "be more selective and avoid chop", source="chat")
  assert st["n_chat_lessons"] == 1
  assert st["tau"] >= 0.52  # default 0.50 + selective lesson delta
  save_state(st, path)
  loaded = load_state(path)
  assert loaded["n_outcome_updates"] == 1
  assert loaded["lessons"]


def test_rules_ledger_mines_stop_loss_and_bans_ticker(tmp_path):
  from processor.hybrid.recognition.learn import apply_outcome, default_state
  from processor.hybrid.recognition.rules_ledger import daily_briefing, rules_clerk_message

  st = default_state()
  st = apply_outcome(
    st,
    asof="2026-08-04",
    messages=[{"agent": "MetaLabel", "vote": "take"}, {"agent": "Regime", "vote": "take"}],
    pnl=-200.0,
    traded=True,
    trades=[{"ticker": "HINDALCO.NS", "pnl": -200.0, "exit_reason": "stop_loss"}],
    regime_label="chop",
  )
  assert st["n_rules"] >= 1
  # ticker cooldown is hard; regime is soft
  assert any(r.get("kind") == "ticker_cooldown" and r.get("severity") == "hard" for r in st["rules"])
  briefing = daily_briefing(st, asof="2026-08-05")
  assert briefing["must_read_before_trade"] is True
  msg, _ = rules_clerk_message(st, asof="2026-08-05", regime_label="chop", candidate_ticker="HINDALCO.NS")
  assert msg.vote == "skip"
  assert msg.payload.get("hard") is True
  # Same day+ticker banned; different ticker with only soft regime should not hard-block
  msg2, _ = rules_clerk_message(st, asof="2026-08-05", regime_label="chop", candidate_ticker="RELIANCE.NS")
  assert msg2.payload.get("hard") is not True
  from processor.hybrid.recognition.swarm.supervisor import decide_agreement
  from processor.hybrid.recognition.types import AgentMessage

  agr = decide_agreement(
    [
      msg,
      AgentMessage(agent="Cost", vote="take", status="ok"),
      AgentMessage(agent="MetaLabel", vote="take", status="ok"),
    ],
    tau=0.4,
    primary_side="buy",
  )
  assert agr.tradeable is False
  assert "RulesClerk" in (agr.reason or "")


def test_dtw_self_distance_small():
  p = DEFAULT_TEMPLATES["trend_up"]
  assert dtw_distance(p, p) < 1e-6


def test_agreement_hard_metalabel_blocks():
  msgs = [
    AgentMessage(agent="Similarity", vote="take", status="ok"),
    AgentMessage(agent="MetaLabel", vote="skip", status="ok", payload={"hard": True, "p_take": 0.2}),
  ]
  agr = decide_agreement(msgs, tau=0.5, primary_side="buy")
  assert agr.tradeable is False


def test_agreement_soft_metalabel_does_not_hard_block():
  msgs = [
    AgentMessage(agent="Similarity", vote="take", status="ok"),
    AgentMessage(agent="LineGeometry", vote="take", status="ok"),
    AgentMessage(agent="MetaLabel", vote="skip", status="ok", payload={"hard": False, "p_take": 0.4}),
    AgentMessage(agent="Cost", vote="take", status="ok"),
  ]
  agr = decide_agreement(msgs, tau=0.5, primary_side="buy")
  assert "MetaLabel" not in (agr.reason or "")


def test_agreement_allows_when_score_ok_despite_soft_skip():
  msgs = [
    AgentMessage(agent="Similarity", vote="take", status="ok"),
    AgentMessage(agent="LineGeometry", vote="take", status="ok"),
    AgentMessage(agent="Regime", vote="skip", status="ok"),
    AgentMessage(agent="Cost", vote="take", status="ok"),
    AgentMessage(agent="MetaLabel", vote="take", status="ok"),
  ]
  agr = decide_agreement(msgs, tau=0.55, primary_side="buy")
  assert agr.score >= 0.55
  assert agr.tradeable is True
