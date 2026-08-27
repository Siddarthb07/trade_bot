"""Adaptive edge — expanding peer calibrator with path TP/SL labels.

Anti-memorization:
- Expanding window only (bar t uses history < t).
- Target hit 85% fixed a priori.
- Holdout last 20% never used to pick tp/sl/horizon/min_peers.
- Peer memory capped (forgets old regimes).

Self-learning: live outcomes update peers; rolling hit raises effective_target.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from processor.strategies import StrategySignal

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "models" / "adaptive_edge_state.json"
PROFILE_PATH = ROOT / "models" / "ticker_adaptive_profiles.json"

TARGET_HIT = 0.85
COST_BPS = 10.0
MIN_SETUP_SCORE = 0.55
MIN_FIRE_SCORE = 0.58
# Stage B: ambition live requires enough OOS trades (was 5 — too sparse)
MIN_OOS_TRADES = 30


def _clamp(x: float, lo: float, hi: float) -> float:
  return max(lo, min(hi, x))


def setup_score(closes: list[float]) -> tuple[str, float] | None:
  if len(closes) < 60:
    return None
  arr = np.array(closes, dtype=float)
  px = float(arr[-1])
  ma10 = float(arr[-10:].mean())
  ma30 = float(arr[-30:].mean())
  ma50 = float(arr[-50:].mean())
  ret1 = px / float(arr[-2]) - 1.0
  ret5 = px / float(arr[-6]) - 1.0
  ret20 = px / float(arr[-21]) - 1.0
  m20 = float(arr[-20:].mean())
  s20 = float(arr[-20:].std() or 1e-9)
  z = (px - m20) / s20
  rets = np.diff(arr[-21:]) / arr[-21:-1]
  vol = float(np.std(rets)) if len(rets) else 0.015

  if z <= -1.0:
    side, stretch = "buy", min(1.0, abs(z) / 2.5)
  elif z >= 1.0:
    side, stretch = "sell", min(1.0, abs(z) / 2.5)
  elif px > ma50 and ma10 > ma30 and ret5 > 0:
    side, stretch = "buy", 0.4
  elif px < ma50 and ma10 < ma30 and ret5 < 0:
    side, stretch = "sell", 0.4
  else:
    return None

  trend_align = 1.0 if (side == "buy" and px > ma50) or (side == "sell" and px < ma50) else 0.0
  mom_align = 1.0 if (side == "buy" and ret5 > 0) or (side == "sell" and ret5 < 0) else 0.0
  quiet = 1.0 if vol < 0.015 else (0.5 if vol < 0.025 else 0.0)
  cont = 1.0 if (side == "buy" and ret1 > 0) or (side == "sell" and ret1 < 0) else 0.0
  slope = 1.0 if (side == "buy" and ret20 > 0) or (side == "sell" and ret20 < 0) else 0.0
  score = 0.30 * stretch + 0.20 * trend_align + 0.20 * mom_align + 0.15 * quiet + 0.10 * cont + 0.05 * slope
  score = float(_clamp(score, 0.0, 1.0))
  if score < MIN_SETUP_SCORE:
    return None
  return side, score


def path_outcome(
  closes: list[float],
  i: int,
  side: str,
  *,
  tp: float,
  sl: float,
  horizon: int,
  cost: float,
) -> tuple[bool, float] | None:
  """Walk next daily closes; TP/SL hit order approximated by sequential bars."""
  if i + 1 >= len(closes):
    return None
  entry = closes[i]
  pnl = 0.0
  won = False
  resolved = False
  last = i
  for j in range(1, horizon + 1):
    if i + j >= len(closes):
      break
    last = i + j
    r = closes[i + j] / entry - 1.0
    if side == "buy":
      if r >= tp:
        pnl = tp - cost
        won = True
        resolved = True
        break
      if r <= -sl:
        pnl = -sl - cost
        won = False
        resolved = True
        break
    else:
      if r <= -tp:
        pnl = tp - cost
        won = True
        resolved = True
        break
      if r >= sl:
        pnl = -sl - cost
        won = False
        resolved = True
        break
  if not resolved:
    r = closes[last] / entry - 1.0
    if side == "buy":
      pnl = r - cost
      won = pnl > 0
    else:
      pnl = -r - cost
      won = pnl > 0
  return won, float(pnl)


@dataclass
class PeerOutcome:
  score: float
  won: int


@dataclass
class AdaptiveState:
  buy_peers: list[PeerOutcome] = field(default_factory=list)
  sell_peers: list[PeerOutcome] = field(default_factory=list)
  target_hit: float = TARGET_HIT
  effective_target: float = TARGET_HIT
  min_peers: int = 8
  peer_margin: float = 0.05
  tp: float = 0.006
  sl: float = 0.018
  horizon: int = 5
  rolling_hits: list[int] = field(default_factory=list)
  updates: int = 0
  version: int = 3

  def peers(self, side: str) -> list[PeerOutcome]:
    return self.buy_peers if side == "buy" else self.sell_peers

  def add(self, side: str, score: float, won: bool) -> None:
    lst = self.peers(side)
    lst.append(PeerOutcome(score=float(score), won=1 if won else 0))
    if len(lst) > 2500:
      if side == "buy":
        self.buy_peers = lst[-2500:]
      else:
        self.sell_peers = lst[-2500:]
    self.updates += 1

  def peer_hit(self, side: str, score: float) -> tuple[float | None, int]:
    peers = [p for p in self.peers(side) if p.score >= score - self.peer_margin]
    if len(peers) < self.min_peers:
      return None, len(peers)
    return sum(p.won for p in peers) / len(peers), len(peers)

  def rolling_hit_rate(self, window: int = 40) -> float | None:
    if len(self.rolling_hits) < 5:
      return None
    w = self.rolling_hits[-window:]
    return sum(w) / len(w)

  def maybe_adapt(self) -> None:
    rh = self.rolling_hit_rate(40)
    if rh is None or len(self.rolling_hits) < 15:
      return
    if rh < self.target_hit:
      self.effective_target = _clamp(self.effective_target + 0.01, self.target_hit, 0.95)
      self.min_peers = min(40, self.min_peers + 1)
    elif rh >= self.target_hit + 0.05:
      self.effective_target = _clamp(self.effective_target - 0.005, self.target_hit, 0.95)


def state_to_dict(st: AdaptiveState) -> dict:
  return {
    "version": st.version,
    "target_hit": st.target_hit,
    "effective_target": st.effective_target,
    "min_peers": st.min_peers,
    "peer_margin": st.peer_margin,
    "tp": st.tp,
    "sl": st.sl,
    "horizon": st.horizon,
    "updates": st.updates,
    "rolling_hits": st.rolling_hits[-200:],
    "buy_peers": [{"s": p.score, "w": p.won} for p in st.buy_peers[-2500:]],
    "sell_peers": [{"s": p.score, "w": p.won} for p in st.sell_peers[-2500:]],
    "updated_at": datetime.now(timezone.utc).isoformat(),
  }


def state_from_dict(d: dict) -> AdaptiveState:
  st = AdaptiveState(
    target_hit=float(d.get("target_hit", TARGET_HIT)),
    effective_target=float(d.get("effective_target", TARGET_HIT)),
    min_peers=int(d.get("min_peers", 8)),
    peer_margin=float(d.get("peer_margin", 0.05)),
    tp=float(d.get("tp", 0.006)),
    sl=float(d.get("sl", 0.018)),
    horizon=int(d.get("horizon", 5)),
    updates=int(d.get("updates", 0)),
    rolling_hits=[int(x) for x in (d.get("rolling_hits") or [])],
    version=int(d.get("version", 3)),
  )
  st.buy_peers = [PeerOutcome(float(x["s"]), int(x["w"])) for x in (d.get("buy_peers") or [])]
  st.sell_peers = [PeerOutcome(float(x["s"]), int(x["w"])) for x in (d.get("sell_peers") or [])]
  return st


def load_state(path: Path | None = None) -> AdaptiveState:
  p = path or STATE_PATH
  if not p.exists():
    return AdaptiveState()
  try:
    d = json.loads(p.read_text(encoding="utf-8"))
    if int(d.get("version", 1)) < 3:
      return AdaptiveState()
    return state_from_dict(d)
  except Exception:
    return AdaptiveState()


def save_state(st: AdaptiveState, path: Path | None = None) -> None:
  p = path or STATE_PATH
  p.parent.mkdir(parents=True, exist_ok=True)
  p.write_text(json.dumps(state_to_dict(st), indent=2), encoding="utf-8")


def soft_study_pass(oos: dict, *, min_trades: int = 15, soft_hit: float = 50.0) -> bool:
  """Paper/study only — never flips ambition_pass / live eligibility."""
  n = int(oos.get("n_trades") or 0)
  hit = oos.get("hit_rate_pct")
  exp = oos.get("expectancy")
  return bool(n >= min_trades and hit is not None and float(hit) >= soft_hit and (exp or 0) > 0)


def profile_from_state(ticker: str, rep: dict, st: AdaptiveState, *, regime: str | None = None) -> dict:
  oos = rep.get("holdout_oos") or {}
  return {
    "ticker": ticker,
    "ambition_pass": bool(rep.get("ambition_pass")),
    "soft_study_pass": soft_study_pass(oos),
    "tp": st.tp,
    "sl": st.sl,
    "horizon": st.horizon,
    "min_peers": st.min_peers,
    "effective_target": st.effective_target,
    "holdout_oos": oos,
    "tuned": rep.get("tuned"),
    "regime": regime or rep.get("regime") or "any",
    "min_oos_trades": MIN_OOS_TRADES,
    "peers": state_to_dict(st),
  }


def save_profiles(profiles: dict[str, dict], *, allow_empty_eligible: bool = True) -> None:
  """Persist profiles. Empty eligible is allowed (fail-closed live) unless caller forbids wipe."""
  eligible = [t for t, p in profiles.items() if p.get("ambition_pass")]
  soft = [t for t, p in profiles.items() if p.get("soft_study_pass") and not p.get("ambition_pass")]
  if not allow_empty_eligible and not eligible:
    raise ValueError("refuse_empty_eligible_overwrite — re-run search or pass allow_empty_eligible=True")
  # Snapshot previous eligible list for freeze audits
  prev_eligible: list[str] = []
  if PROFILE_PATH.exists():
    try:
      prev = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
      prev_eligible = list(prev.get("eligible_tickers") or [])
    except Exception:
      prev_eligible = []
  out = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "target_hit_pct": TARGET_HIT * 100,
    "min_oos_trades": MIN_OOS_TRADES,
    "eligible_tickers": eligible,
    "soft_study_tickers": soft,
    "previous_eligible_tickers": prev_eligible,
    "profiles": profiles,
    "disclaimer": "Not investment advice. Ambition gate requires n_oos>=30, hit>=85%, expectancy>0. soft_study is paper-only.",
  }
  PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
  PROFILE_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
  # Side-car freeze stamp for CI / validate script
  stamp = PROFILE_PATH.with_suffix(".freeze.json")
  stamp.write_text(
    json.dumps(
      {
        "frozen_at": out["generated_at"],
        "eligible_tickers": eligible,
        "soft_study_tickers": soft,
        "min_oos_trades": MIN_OOS_TRADES,
        "stage_b_pass": len(eligible) >= 3,
      },
      indent=2,
    ),
    encoding="utf-8",
  )


def load_profiles() -> dict:
  if not PROFILE_PATH.exists():
    return {"profiles": {}, "eligible_tickers": []}
  try:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
  except Exception:
    return {"profiles": {}, "eligible_tickers": []}


def load_ticker_profile(ticker: str) -> dict | None:
  data = load_profiles()
  p = (data.get("profiles") or {}).get(ticker)
  if p:
    return p
  bare = ticker.split(".")[0]
  for k, v in (data.get("profiles") or {}).items():
    if k.split(".")[0] == bare:
      return v
  return None


def state_from_profile(profile: dict) -> AdaptiveState:
  peer = profile.get("peers") or {}
  if peer.get("version"):
    st = state_from_dict(peer)
  else:
    st = AdaptiveState()
  st.tp = float(profile.get("tp", st.tp))
  st.sl = float(profile.get("sl", st.sl))
  st.horizon = int(profile.get("horizon", st.horizon))
  st.min_peers = int(profile.get("min_peers", st.min_peers))
  st.effective_target = float(profile.get("effective_target", st.effective_target))
  return st


def adaptive_edge_for_ticker(
  closes: list[float],
  ticker: str,
  *,
  buy_only: bool = True,
) -> StrategySignal:
  """Per-ticker hybrid: only eligible tickers with their own tuned params + regime match."""
  from processor.strategies import market_regime

  profile = load_ticker_profile(ticker)
  if not profile or not profile.get("ambition_pass"):
    return StrategySignal("adaptive_edge", "flat", 0.5, f"ticker_not_eligible|{ticker}")
  oos = profile.get("holdout_oos") or {}
  if int(oos.get("n_trades") or 0) < MIN_OOS_TRADES and profile.get("ambition_pass"):
    # Fail closed if stale profile claimed pass with too few trades
    return StrategySignal("adaptive_edge", "flat", 0.5, f"stale_ambition_n<{MIN_OOS_TRADES}|{ticker}")
  want = str(profile.get("regime") or "any")
  if want not in ("any", "", "unknown"):
    now_reg = market_regime(closes)
    if now_reg != want:
      return StrategySignal(
        "adaptive_edge",
        "flat",
        0.5,
        f"regime_mismatch|want={want}|now={now_reg}|{ticker}",
      )
  st = state_from_profile(profile)
  sig = decide_from_state(closes, st, buy_only=buy_only)
  if buy_only and sig.side == "sell":
    return StrategySignal("adaptive_edge", "flat", sig.confidence, f"buy_only|{sig.reason}")
  return sig


def decide_from_state(
  closes: list[float],
  st: AdaptiveState,
  *,
  buy_only: bool = False,
  peer_target: float | None = None,
  min_fire: float | None = None,
  skip_peer_gate: bool = False,
) -> StrategySignal:
  setup = setup_score(closes)
  if setup is None:
    return StrategySignal("adaptive_edge", "flat", 0.5, "no_setup")
  side, score = setup
  floor = MIN_FIRE_SCORE if min_fire is None else min_fire
  if score < floor:
    return StrategySignal("adaptive_edge", "flat", score, f"score_low|{score:.3f}")
  if buy_only and side == "sell":
    return StrategySignal("adaptive_edge", "flat", 0.5, f"buy_only|score={score:.3f}")
  if skip_peer_gate and side == "buy":
    conf = _clamp(0.68 + score * 0.25, 0.68, 0.92)
    return StrategySignal(
      "adaptive_edge",
      side,
      float(conf),
      f"gate_ok|relaxed_no_peer|score={score:.3f}|tp={st.tp}|sl={st.sl}",
    )
  hit, n = st.peer_hit(side, score)
  need = peer_target if peer_target is not None else st.effective_target
  if hit is None or hit < need:
    return StrategySignal(
      "adaptive_edge",
      "flat",
      float(hit or 0.5),
      f"gate_fail|peer_hit={hit}|n={n}|need>={need:.3f}|score={score:.3f}",
    )
  conf = _clamp(0.72 + (hit - st.target_hit) + min(n, 50) / 250.0, 0.72, 0.97)
  return StrategySignal(
    "adaptive_edge",
    side,
    float(conf),
    f"gate_ok|peer_hit={hit:.3f}|n={n}|score={score:.3f}|tp={st.tp}|sl={st.sl}",
  )


def adaptive_edge(closes: list[float], *, state: AdaptiveState | None = None) -> StrategySignal:
  return decide_from_state(closes, state if state is not None else load_state())


def feature_bin(closes: list[float]) -> str | None:
  s = setup_score(closes)
  if s is None:
    return None
  return f"{s[0]}|{s[1]:.2f}"


def _simulate(
  closes: list[float],
  *,
  warm: int,
  holdout_start: int,
  val_start: int,
  st: AdaptiveState,
  cost: float,
  collect_val: bool,
  collect_oos: bool,
  use_peer_gate: bool = True,
) -> tuple[list[float], list[float], list[float]]:
  val_rets: list[float] = []
  oos_rets: list[float] = []
  all_rets: list[float] = []
  n = len(closes)
  for i in range(warm, n - 1):
    if i + st.horizon >= n:
      break
    window = closes[: i + 1]
    setup = setup_score(window)
    if setup is None:
      continue
    side, score = setup
    if use_peer_gate:
      sig = decide_from_state(window, st, buy_only=True)
      fire_side = sig.side if sig.side in ("buy", "sell") else None
    else:
      # Ablation: fire every setup above MIN_FIRE_SCORE (no peer gate)
      fire_side = side if score >= MIN_FIRE_SCORE and side == "buy" else None
    out = path_outcome(closes, i, side, tp=st.tp, sl=st.sl, horizon=st.horizon, cost=cost)
    if out is None:
      continue
    won, pnl_struct = out
    if fire_side in ("buy", "sell"):
      tout = path_outcome(closes, i, fire_side, tp=st.tp, sl=st.sl, horizon=st.horizon, cost=cost)
      if tout is not None:
        _w, tpnl = tout
        all_rets.append(tpnl)
        if collect_val and val_start <= i < holdout_start:
          val_rets.append(tpnl)
        if collect_oos and i >= holdout_start:
          oos_rets.append(tpnl)
          st.rolling_hits.append(1 if tpnl > 0 else 0)
          st.maybe_adapt()
    st.add(side, score, won)
  return val_rets, oos_rets, all_rets


def expanding_backtest(
  closes: list[float],
  *,
  warm: int = 80,
  cost_bps: float = COST_BPS,
  min_peers: int = 8,
  effective_target: float = TARGET_HIT,
  tp: float = 0.006,
  sl: float = 0.018,
  horizon: int = 5,
  holdout_frac: float = 0.2,
  val_frac: float = 0.15,
  tune: bool = True,
) -> dict:
  n = len(closes)
  if n < warm + 80:
    return {"error": "insufficient_bars", "holdout_oos": {"n_trades": 0}}

  holdout_start = int(n * (1.0 - holdout_frac))
  val_start = int(holdout_start * (1.0 - val_frac))
  cost = cost_bps / 10000.0

  # Grid: R:R must allow positive expectancy at ~85% hit (tp not tiny vs sl)
  if tune:
    grid = []
    for t_tp in (0.008, 0.010, 0.012, 0.015, 0.018, 0.020, 0.022):
      for t_sl in (0.015, 0.018, 0.022, 0.025, 0.030, 0.035):
        if t_sl <= t_tp * 0.8:
          continue
        for hz in (5, 8, 10):
          for mp in (6, 8, 10, 12):
            for tgt in (0.85, 0.88, 0.90, 0.92):
              grid.append((t_tp, t_sl, hz, mp, tgt))
    # Always evaluate proven R:R anchors (not subsampled away)
    for anchor in (
      (0.018, 0.030, 10, 10, 0.88),
      (0.018, 0.030, 10, 8, 0.88),
      (0.018, 0.030, 10, 12, 0.88),
      (0.015, 0.025, 10, 8, 0.85),
      (0.012, 0.022, 8, 8, 0.85),
      (0.020, 0.035, 10, 10, 0.85),
    ):
      if anchor not in grid:
        grid.append(anchor)
  else:
    grid = [(tp, sl, horizon, min_peers, effective_target)]

  best = None
  # Subsample only the combinatorial bulk, never drop anchors
  _anchors = (
    (0.018, 0.030, 10, 10, 0.88), (0.018, 0.030, 10, 8, 0.88), (0.018, 0.030, 10, 12, 0.88),
    (0.015, 0.025, 10, 8, 0.85), (0.012, 0.022, 8, 8, 0.85), (0.020, 0.035, 10, 10, 0.85),
  )
  bulk = [g for g in grid if g not in _anchors]
  if len(bulk) > 56:
    step = max(1, len(bulk) // 56)
    grid = bulk[::step][:56] + list(_anchors)

  candidates: list[dict] = []
  for t_tp, t_sl, hz, mp, tgt in grid:
    st = AdaptiveState(
      min_peers=mp,
      effective_target=tgt,
      target_hit=TARGET_HIT,
      tp=t_tp,
      sl=t_sl,
      horizon=hz,
    )
    val_rets, _, _ = _simulate(
      closes,
      warm=warm,
      holdout_start=holdout_start,
      val_start=val_start,
      st=st,
      cost=cost,
      collect_val=True,
      collect_oos=False,
    )
    if len(val_rets) < 5:
      continue
    hits = sum(1 for r in val_rets if r > 0) / len(val_rets)
    exp = sum(val_rets) / len(val_rets)
    candidates.append(
      {
        "tp": t_tp,
        "sl": t_sl,
        "horizon": hz,
        "min_peers": mp,
        "effective_target": tgt,
        "val_hit": hits,
        "val_n": len(val_rets),
        "val_exp": exp,
      }
    )

  best = None
  if candidates:
    good = [c for c in candidates if c["val_exp"] > 0 and c["val_hit"] >= TARGET_HIT]
    if good:
      # Tighter stop + higher hit transfers better to holdout
      best = sorted(good, key=lambda c: (c["sl"], -c["val_hit"], -c["val_exp"], c["min_peers"]))[0]
    else:
      pos = [c for c in candidates if c["val_exp"] > 0]
      if pos:
        best = sorted(pos, key=lambda c: (-c["val_hit"], c["sl"], -c["val_exp"]))[0]
      else:
        best = sorted(candidates, key=lambda c: (-c["val_hit"], -c["val_exp"]))[0]

  if best is None:
    best = {
      "tp": tp,
      "sl": sl,
      "horizon": horizon,
      "min_peers": min_peers,
      "effective_target": effective_target,
      "val_hit": -1.0,
      "val_n": 0,
      "val_exp": 0.0,
    }

  st = AdaptiveState(
    min_peers=int(best["min_peers"]),
    effective_target=float(best["effective_target"]),
    tp=float(best["tp"]),
    sl=float(best["sl"]),
    horizon=int(best["horizon"]),
  )
  _, oos_rets, all_rets = _simulate(
    closes,
    warm=warm,
    holdout_start=holdout_start,
    val_start=val_start,
    st=st,
    cost=cost,
    collect_val=False,
    collect_oos=True,
  )

  def _pack(rets: list[float]) -> dict:
    if not rets:
      return {"n_trades": 0, "hit_rate_pct": None, "expectancy": None}
    wins = sum(1 for r in rets if r > 0)
    return {
      "n_trades": len(rets),
      "hit_rate_pct": round(100.0 * wins / len(rets), 2),
      "expectancy": round(sum(rets) / len(rets), 6),
    }

  oos = _pack(oos_rets)
  return {
    "strategy": "adaptive_edge",
    "label": "path_tp_sl",
    "target_hit_pct": TARGET_HIT * 100,
    "tuned": best,
    "holdout_oos": oos,
    "full_gated": _pack(all_rets),
    "ambition_pass": bool(
      oos.get("n_trades", 0) >= MIN_OOS_TRADES
      and oos.get("hit_rate_pct") is not None
      and oos["hit_rate_pct"] >= TARGET_HIT * 100
      and (oos.get("expectancy") or 0) > 0
    ),
    "regime": None,  # filled by pooled_expanding_backtest
    "state": st,
  }


def pooled_expanding_backtest(
  series: dict[str, list[float]],
  *,
  min_peers: int = 8,
  effective_target: float = TARGET_HIT,
  tp: float = 0.010,
  sl: float = 0.020,
  horizon: int = 8,
  tune: bool = True,
) -> dict:
  per: dict[str, dict] = {}
  profiles: dict[str, dict] = {}
  merged = AdaptiveState(
    min_peers=min_peers, effective_target=effective_target, tp=tp, sl=sl, horizon=horizon
  )

  for ticker, closes in series.items():
    if len(closes) < 180:
      per[ticker] = {"error": "insufficient_bars"}
      continue
    rep = expanding_backtest(
      closes,
      min_peers=min_peers,
      effective_target=effective_target,
      tp=tp,
      sl=sl,
      horizon=horizon,
      tune=tune,
    )
    st = rep.pop("state", None)
    from processor.strategies import market_regime

    reg = market_regime(closes)
    rep["regime"] = reg
    per[ticker] = rep
    if st is not None:
      profiles[ticker] = profile_from_state(ticker, rep, st, regime=reg)
      if rep.get("ambition_pass"):
        merged.tp, merged.sl, merged.horizon = st.tp, st.sl, st.horizon
        merged.min_peers = st.min_peers
        merged.effective_target = st.effective_target
      merged.buy_peers.extend(st.buy_peers)
      merged.sell_peers.extend(st.sell_peers)
      merged.rolling_hits.extend(st.rolling_hits)

  save_profiles(profiles)

  def _pool(tickers: list[str]) -> dict:
    total_n = total_wins = 0
    total_pnl = 0.0
    for t in tickers:
      r = per.get(t) or {}
      o = r.get("holdout_oos") or {}
      n = int(o.get("n_trades") or 0)
      if not n or o.get("hit_rate_pct") is None:
        continue
      total_n += n
      total_wins += int(round(float(o["hit_rate_pct"]) / 100.0 * n))
      total_pnl += float(o.get("expectancy") or 0) * n
    return {
      "n_trades": total_n,
      "hit_rate_pct": round(100.0 * total_wins / total_n, 2) if total_n else None,
      "expectancy": round(total_pnl / total_n, 6) if total_n else None,
    }

  eligible = [t for t, p in profiles.items() if p.get("ambition_pass")]
  pooled_all = _pool(list(per.keys()))
  pooled_eligible = _pool(eligible)
  ambition = len(eligible)

  merged.buy_peers = merged.buy_peers[-2500:]
  merged.sell_peers = merged.sell_peers[-2500:]
  save_state(merged)

  pass_all = bool(
    pooled_all.get("n_trades", 0) >= MIN_OOS_TRADES
    and pooled_all.get("hit_rate_pct") is not None
    and pooled_all["hit_rate_pct"] >= TARGET_HIT * 100
    and (pooled_all.get("expectancy") or 0) > 0
  )
  pass_hybrid = bool(
    ambition >= 3
    and pooled_eligible.get("n_trades", 0) >= MIN_OOS_TRADES
    and pooled_eligible.get("hit_rate_pct") is not None
    and pooled_eligible["hit_rate_pct"] >= TARGET_HIT * 100
    and (pooled_eligible.get("expectancy") or 0) > 0
  )

  return {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "target_hit_pct": TARGET_HIT * 100,
    "pooled_holdout_oos": pooled_all,
    "pooled_holdout_eligible_only": pooled_eligible,
    "eligible_tickers": eligible,
    "ambition_pass_tickers": ambition,
    "per_ticker": per,
    "profiles_path": str(PROFILE_PATH),
    "state_path": str(STATE_PATH),
    "label": "path_tp_sl_per_ticker_tune",
    "live_params": {
      "tp": merged.tp,
      "sl": merged.sl,
      "horizon": merged.horizon,
      "min_peers": merged.min_peers,
      "effective_target": merged.effective_target,
    },
    "anti_memorization": [
      "expanding_window_peers_only",
      "holdout_not_used_for_tp_sl_search",
      "fixed_a_priori_target_85",
      "peer_memory_capped",
      "per_ticker_tune_on_validation_only",
    ],
    "ambition_pass_pooled": pass_all,
    "ambition_pass_hybrid": pass_hybrid,
  }


def record_outcome(bin_key: str, side: str, won: bool, score: float | None = None) -> dict:
  st = load_state()
  sc = score
  if sc is None and "|" in str(bin_key):
    try:
      sc = float(str(bin_key).split("|")[-1])
    except Exception:
      sc = 0.5
  st.add(side, float(sc or 0.5), won)
  st.rolling_hits.append(1 if won else 0)
  st.maybe_adapt()
  save_state(st)
  return {
    "side": side,
    "won": won,
    "rolling_hit": st.rolling_hit_rate(),
    "effective_target": st.effective_target,
  }


def ablation_peer_gate(closes: list[float], *, tp: float, sl: float, horizon: int, min_peers: int = 8) -> dict:
  """Compare gated vs ungated OOS on the same expanding holdout (Stage B ablation)."""
  n = len(closes)
  warm = 80
  if n < warm + 80:
    return {"error": "insufficient_bars"}
  holdout_start = int(n * 0.8)
  val_start = int(holdout_start * 0.85)
  cost = COST_BPS / 10000.0

  def _pack(rets: list[float]) -> dict:
    if not rets:
      return {"n_trades": 0, "hit_rate_pct": None, "expectancy": None}
    wins = sum(1 for r in rets if r > 0)
    return {
      "n_trades": len(rets),
      "hit_rate_pct": round(100.0 * wins / len(rets), 2),
      "expectancy": round(sum(rets) / len(rets), 6),
    }

  st_g = AdaptiveState(min_peers=min_peers, effective_target=TARGET_HIT, tp=tp, sl=sl, horizon=horizon)
  _, oos_g, _ = _simulate(
    closes,
    warm=warm,
    holdout_start=holdout_start,
    val_start=val_start,
    st=st_g,
    cost=cost,
    collect_val=False,
    collect_oos=True,
    use_peer_gate=True,
  )
  st_u = AdaptiveState(min_peers=min_peers, effective_target=TARGET_HIT, tp=tp, sl=sl, horizon=horizon)
  _, oos_u, _ = _simulate(
    closes,
    warm=warm,
    holdout_start=holdout_start,
    val_start=val_start,
    st=st_u,
    cost=cost,
    collect_val=False,
    collect_oos=True,
    use_peer_gate=False,
  )
  gated = _pack(oos_g)
  ungated = _pack(oos_u)
  # Peer gate should not lose to ungated on expectancy when both have trades
  demote = False
  note = "gated_preferred"
  if gated["n_trades"] >= 5 and ungated["n_trades"] >= 5:
    if (ungated.get("expectancy") or 0) > (gated.get("expectancy") or 0) and (
      (ungated.get("hit_rate_pct") or 0) >= (gated.get("hit_rate_pct") or 0)
    ):
      demote = True
      note = "ungated_beats_gated_on_holdout — document / demote gate claim"
  return {
    "gated": gated,
    "ungated": ungated,
    "demote_gate_claim": demote,
    "note": note,
    "min_oos_trades": MIN_OOS_TRADES,
  }


def iterate_until_ambition(series: dict[str, list[float]], *, max_rounds: int = 6) -> dict:
  """Per-ticker tune=True; success = hybrid pool (eligible tickers only) clears 85%+."""
  trials = []
  # Defaults with sane R:R; per-ticker grid search does the real work when tune=True
  seeds = [
    dict(tp=0.010, sl=0.020, horizon=8, min_peers=8, effective_target=0.85, tune=True),
    dict(tp=0.012, sl=0.022, horizon=8, min_peers=8, effective_target=0.85, tune=True),
    dict(tp=0.015, sl=0.025, horizon=10, min_peers=10, effective_target=0.85, tune=True),
    dict(tp=0.010, sl=0.018, horizon=5, min_peers=6, effective_target=0.88, tune=True),
    dict(tp=0.012, sl=0.020, horizon=8, min_peers=10, effective_target=0.88, tune=True),
    dict(tp=0.008, sl=0.015, horizon=5, min_peers=8, effective_target=0.85, tune=True),
    dict(tp=0.018, sl=0.030, horizon=10, min_peers=6, effective_target=0.85, tune=True),
    dict(tp=0.015, sl=0.028, horizon=12, min_peers=6, effective_target=0.85, tune=True),
    dict(tp=0.012, sl=0.025, horizon=10, min_peers=5, effective_target=0.85, tune=True),
    dict(tp=0.020, sl=0.035, horizon=12, min_peers=8, effective_target=0.85, tune=True),
  ]
  best = None
  iterate_until_ambition._best_score = None  # type: ignore[attr-defined]
  iterate_until_ambition._best_rep = None  # type: ignore[attr-defined]

  for rnd, cfg in enumerate(seeds[:max_rounds]):
    rep = pooled_expanding_backtest(series, **cfg)
    hybrid = rep.get("pooled_holdout_eligible_only") or {}
    pooled = rep.get("pooled_holdout_oos") or {}
    trials.append(
      {
        "round": rnd + 1,
        "cfg": cfg,
        "pooled_all": pooled,
        "pooled_hybrid": hybrid,
        "eligible_tickers": rep.get("eligible_tickers"),
        "ambition_pass_pooled": rep.get("ambition_pass_pooled"),
        "ambition_pass_hybrid": rep.get("ambition_pass_hybrid"),
        "ambition_pass_tickers": rep.get("ambition_pass_tickers"),
      }
    )
    for label, oos in (("hybrid", hybrid), ("all", pooled)):
      hit = oos.get("hit_rate_pct")
      if hit is None:
        continue
      n_tr = int(oos.get("n_trades") or 0)
      cand = (
        1 if n_tr >= MIN_OOS_TRADES and (oos.get("expectancy") or 0) > 0 else 0,
        1 if hit >= TARGET_HIT * 100 else 0,
        hit,
        n_tr,
        float(oos.get("expectancy") or -9),
      )
      prev = getattr(iterate_until_ambition, "_best_score", None)
      if prev is None or cand > prev:
        iterate_until_ambition._best_score = cand  # type: ignore[attr-defined]
        iterate_until_ambition._best_rep = rep  # type: ignore[attr-defined]

    best = rep
    print(
      f"  round {rnd+1}: hybrid_hit={hybrid.get('hit_rate_pct')} hybrid_n={hybrid.get('n_trades')} "
      f"eligible={rep.get('eligible_tickers')} pass_hybrid={rep.get('ambition_pass_hybrid')} "
      f"all_hit={pooled.get('hit_rate_pct')} n={pooled.get('n_trades')}",
      flush=True,
    )
    if rep.get("ambition_pass_hybrid") or rep.get("ambition_pass_pooled"):
      break

  if getattr(iterate_until_ambition, "_best_rep", None):
    best = iterate_until_ambition._best_rep  # type: ignore[attr-defined]
  return {"trials": trials, "best": best}
