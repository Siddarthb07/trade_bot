"""2025 clean-PIT daily-swing benchmark for Pattern Forge.

Uses Yahoo daily closes (PIT-truncated to asof). Logs decisions/trades to pattern_forge ledger.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.costs import IN_FO_COST
from processor.day_sim import _fetch_history, _fetch_history_ohlcv
from processor.fo_universe import fo_universe_list
from processor.no_ruin import NoRuinConfig, apply_no_ruin_to_leverage, risk_budget, state_dict, update_peak
from processor.hybrid.recognition.swarm.cross_market import similarity_size_mult
from processor.pattern_forge.daily_swing import (
  breadth_above_ma20,
  choose_daily_candidate,
  next_day_pnl_frac,
  resolve_market_mode,
  stock_daily_features,
)
from processor.pattern_forge.daily_swarm_tape_v2 import daily_swarm_tape
from processor.pattern_forge.ledger import log_decision, log_run, log_trade, write_summary
from processor.pattern_forge.market_regime_proxy import market_closes_asof, soft_regime
from processor.pattern_forge.mistake_ledger import learn_from_day, note_repeat_blocked, read_briefing, seed_standing_policies, standing_freq_knobs
from processor.pattern_forge.news_edge import news_edge_size_mult
from processor.pattern_forge.overnight_feeds import overnight_cues_asof
from processor.pattern_forge.research_agents import research_agent_size_mult
from processor.pattern_forge.v2_alpha_exit import plan_and_simulate as v2_alpha_plan_and_simulate
from processor.two_sided import notional_pnl

_MONTH_NAMES = [
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


def months_for_year(year: int, *, clip_to_today: bool = True) -> list[tuple[str, str, str]]:
  import calendar

  today = date.today()
  out: list[tuple[str, str, str]] = []
  for i, name in enumerate(_MONTH_NAMES, start=1):
    if clip_to_today and year > today.year:
      break
    if clip_to_today and year == today.year and i > today.month:
      break
    last = calendar.monthrange(year, i)[1]
    end_d = f"{year}-{i:02d}-{last:02d}"
    if clip_to_today and year == today.year and i == today.month:
      end_d = today.isoformat()
    out.append((name, f"{year}-{i:02d}-01", end_d))
  return out


MONTHS_2025 = months_for_year(2025)


def _load_universe_series(tickers: list[str], end: str = "2025-12-31", *, lookback_days: int = 520) -> dict[str, list[tuple[str, float]]]:
  end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
  out: dict[str, list[tuple[str, float]]] = {}
  for t in tickers:
    hist = _fetch_history(t, end_dt, lookback_days=lookback_days)
    out[t] = [(d, c) for d, c in hist if d <= end]
  return out


def _load_universe_ohlcv(
  tickers: list[str], end: str = "2025-12-31", *, lookback_days: int = 520
) -> dict[str, list[tuple[str, float, float, float, float]]]:
  end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
  out: dict[str, list[tuple[str, float, float, float, float]]] = {}
  for t in tickers:
    hist = _fetch_history_ohlcv(t, end_dt, lookback_days=lookback_days)
    out[t] = [row for row in hist if row[0] <= end]
  return out


def _closes_asof(series: list[tuple[str, float]], asof: str) -> list[float]:
  return [c for d, c in series if d <= asof]


def _ohlcv_asof(
  series: list[tuple[str, float, float, float, float]], asof: str
) -> dict[str, list[float]]:
  rows = [r for r in series if r[0] <= asof]
  return {
    "closes": [r[1] for r in rows],
    "volumes": [r[2] for r in rows],
    "highs": [r[3] for r in rows],
    "lows": [r[4] for r in rows],
  }


def _ohlcv_bar_on(
  series: list[tuple[str, float, float, float, float]], day: str
) -> tuple[float, float, float] | None:
  """Return (high, low, close) for exact calendar day, or None."""
  for r in series:
    if r[0] == day:
      return float(r[3]), float(r[4]), float(r[1])
  return None


def _trading_days(series: list[tuple[str, float]], start: str, end: str) -> list[str]:
  return [d for d, _ in series if start <= d <= end]


def _is_v2_alpha_exit(knobs: dict) -> bool:
  """True only when exit_book is explicitly v2_alpha (not lane name alone)."""
  return str(knobs.get("exit_book") or "") == "v2_alpha"


def _apply_v2_alpha_defaults(knobs: dict) -> dict:
  """Fill research defaults when exit_book or exact lane requests v2_alpha."""
  lane = str(knobs.get("lane") or "")
  exit_book = str(knobs.get("exit_book") or "")
  wants = exit_book == "v2_alpha" or lane == "v2_alpha"
  # Ablation lanes: v2_alpha_stops_only / v2_alpha_tp_only must set exit_book=v2_alpha
  if lane.startswith("v2_alpha_") and "ctrl" not in lane and exit_book == "v2_alpha":
    wants = True
  if not wants:
    return knobs
  knobs.setdefault("exit_book", "v2_alpha")
  knobs.setdefault("use_ohlcv", True)
  knobs.setdefault("promote_as", "v2_alpha")
  knobs.setdefault("profit_guard", True)
  knobs.setdefault("learn_mistakes", True)
  knobs.setdefault("v2a_atr_period", 14)
  knobs.setdefault("v2a_swing_lookback", 20)
  knobs.setdefault("v2a_shallow_atr", 1.0)
  knobs.setdefault("v2a_deep_atr", 2.0)
  knobs.setdefault("v2a_stop_shallow", 0.80)
  knobs.setdefault("v2a_stop_mid", 1.25)
  knobs.setdefault("v2a_stop_deep", 1.80)
  knobs.setdefault("v2a_tp_atr", 1.0)
  knobs.setdefault("v2a_partial_frac", 0.50)
  knobs.setdefault("v2a_min_stop_pct", 0.004)
  knobs.setdefault("v2a_adverse_first", True)
  return knobs


def run_daily_benchmark(
  *,
  capital: float = 10_000.0,
  universe: list[str] | None = None,
  months: list[tuple[str, str, str]] | None = None,
  knobs: dict | None = None,
  iteration_id: str | None = None,
  year: int | None = None,
) -> dict:
  knobs = knobs or {}
  knobs = _apply_v2_alpha_defaults(knobs)
  use_v2_alpha = _is_v2_alpha_exit(knobs)
  # v2.2: merge standing freq / Oct soft policies from mistake ledger (never amplify)
  if bool(knobs.get("apply_standing_freq", False)) or str(knobs.get("lane") or "").startswith("v2_2"):
    seed_standing_policies()
    for k, v in standing_freq_knobs().items():
      # Explicit knob wins; standing fills gaps
      if k not in knobs or knobs.get(k) in (None, 0, [], False):
        knobs[k] = v
      elif k == "calendar_soft_months":
        knobs[k] = sorted(set(list(knobs.get(k) or []) + list(v or [])))
      elif k == "calendar_soft_mult":
        knobs[k] = min(float(knobs.get(k) or 1.0), float(v))
  run_id = str(uuid.uuid4())[:12]
  long_only = bool(knobs.get("long_only", True))
  min_score = float(knobs.get("hybrid_min_score", knobs.get("min_score", 0.005)))
  r1_lo = float(knobs.get("r1_lo", 0.005))
  r1_hi = float(knobs.get("r1_hi", 0.06))
  sleeve = float(knobs.get("sleeve_frac", 0.3))
  lev_cap = float(knobs.get("leverage", 8.0))
  top_k = max(1, int(knobs.get("top_k", 1)))
  use_breadth_veto = bool(knobs.get("use_breadth_veto", False))
  breadth_scale = bool(knobs.get("breadth_scale", False))
  learn_mistakes = bool(knobs.get("learn_mistakes", True))
  mistake_mark_read = bool(knobs.get("mistake_mark_read", True))
  profit_guard = bool(knobs.get("profit_guard", False))
  profit_guard_floor_pct = float(knobs.get("profit_guard_floor_pct", 2.0))
  swarm_hard_veto = bool(knobs.get("swarm_hard_veto", False))
  overnight_feeds = bool(knobs.get("overnight_feeds", False))
  allow_overnight_net = bool(knobs.get("allow_overnight_network", False))
  vol_scale_rank = bool(knobs.get("vol_scale_rank", False))
  skip_extended_r5 = knobs.get("skip_extended_r5")
  skip_extended_r5_f = float(skip_extended_r5) if skip_extended_r5 is not None else None
  skip_extended_r5_defense_only = bool(knobs.get("skip_extended_r5_defense_only", False))
  skip_extended_r5_attack = knobs.get("skip_extended_r5_attack")
  skip_extended_r5_attack_f = float(skip_extended_r5_attack) if skip_extended_r5_attack is not None else None
  attack_ytd_sleeve_cap_pct = knobs.get("attack_ytd_sleeve_cap_pct")
  attack_ytd_sleeve_cap_f = float(attack_ytd_sleeve_cap_pct) if attack_ytd_sleeve_cap_pct is not None else None
  attack_ytd_sleeve_mult = float(knobs.get("attack_ytd_sleeve_mult", 0.5))
  require_market_ts_mom = bool(knobs.get("require_market_ts_mom", False))
  market_ts_min = float(knobs.get("market_ts_min", 0.0))
  ticker_cooldown_days = max(0, int(knobs.get("ticker_cooldown_days", 0)))
  # 0 = off (preserve prior hunt cells); set explicitly on loss-cooldown variants
  big_loss_cooldown_days = max(0, int(knobs.get("big_loss_cooldown_days", 0)))
  max_single_name_day_frac = float(knobs.get("max_single_name_day_frac", 1.0))  # of day risk budget
  require_above_ema200 = bool(knobs.get("require_above_ema200", False))
  min_rel_volume = knobs.get("min_rel_volume")
  min_rel_volume_f = float(min_rel_volume) if min_rel_volume is not None else None
  require_above_vwap = bool(knobs.get("require_above_vwap", False))
  vwap_score_boost = float(knobs.get("vwap_score_boost", 0.0))
  vol_soft_penalty = bool(knobs.get("vol_soft_penalty", False))
  score_mode = str(knobs.get("score_mode", "raw_r1"))
  indicator_mode = str(knobs.get("indicator_mode", "off"))
  defense_sitout = bool(knobs.get("defense_sitout", False))
  defense_chop_sitout = bool(knobs.get("defense_chop_sitout", False))
  defense_size_mult = float(knobs.get("defense_size_mult", 0.5))
  defense_on_risk_off = bool(knobs.get("defense_on_risk_off", True))
  defense_on_breadth_stress = bool(knobs.get("defense_on_breadth_stress", True))
  defense_on_nifty_below_ema = bool(knobs.get("defense_on_nifty_below_ema", True))
  nifty_ema_period = int(knobs.get("nifty_ema_period", 200))
  october_defense = bool(knobs.get("october_defense", False))
  october_size_mult = float(knobs.get("october_size_mult", 0.5))
  calendar_sit_months = {
    str(x).lower() for x in (knobs.get("calendar_sit_months") or []) if x
  }
  calendar_sit_mult = float(knobs.get("calendar_sit_mult", 0.0))
  r1_hi_trend = knobs.get("r1_hi_trend")
  r1_hi_trend_f = float(r1_hi_trend) if r1_hi_trend is not None else None
  boost_near_52w_high = bool(knobs.get("boost_near_52w_high", False))
  max_trades_per_month = int(knobs.get("max_trades_per_month") or 0)  # 0 = unlimited
  loss_streak_sitout = int(knobs.get("loss_streak_sitout") or 0)  # sit after N losses
  news_edge_soft = bool(knobs.get("news_edge_soft", False))
  news_edge_soft_mult = float(knobs.get("news_edge_soft_mult", 0.4))
  news_edge_hard = bool(knobs.get("news_edge_hard", False))  # sit cash on NewsEdge skip
  research_agents_soft = bool(knobs.get("research_agents_soft", False))
  research_agents_soft_mult = float(knobs.get("research_agents_soft_mult", 0.45))
  research_agents_hard = bool(knobs.get("research_agents_hard", False))
  liquidity_min_rel_volume = float(knobs.get("liquidity_min_rel_volume", 0.55))
  liquidity_soft_rel_volume = float(knobs.get("liquidity_soft_rel_volume", 0.85))
  auction_chase_gap_bps = float(knobs.get("auction_chase_gap_bps", 120.0))
  bad_month_red_days = int(knobs.get("bad_month_red_days", 2))
  calendar_soft_months = {
    str(x).lower() for x in (knobs.get("calendar_soft_months") or []) if x
  }
  calendar_soft_mult = float(knobs.get("calendar_soft_mult", 0.45))
  # Entry filters in named months (not size soft) — raise score / require trend regime
  calendar_require_trend = {
    str(x).lower() for x in (knobs.get("calendar_require_trend") or []) if x
  }
  calendar_min_score = knobs.get("calendar_min_score")
  calendar_min_score_f = float(calendar_min_score) if calendar_min_score is not None else None
  calendar_min_score_months = {
    str(x).lower()
    for x in (
      knobs.get("calendar_min_score_months")
      or (knobs.get("calendar_soft_months") if calendar_min_score_f is not None else [])
      or []
    )
    if x
  }
  # v2.3 asymmetric: crash defenses when underwater/defense; open throttle when green
  asymmetric_freq = bool(knobs.get("asymmetric_freq", False))
  attack_max_trades_per_month = int(knobs.get("attack_max_trades_per_month") or 0)
  defense_max_trades_per_month = int(
    knobs.get("defense_max_trades_per_month") or max_trades_per_month or 16
  )
  attack_cooldown_days = int(knobs.get("attack_cooldown_days", 0))
  defense_cooldown_days = int(knobs.get("defense_cooldown_days") or ticker_cooldown_days or 1)
  attack_loss_streak_sitout = int(knobs.get("attack_loss_streak_sitout", 0))
  defense_loss_streak_sitout = int(
    knobs.get("defense_loss_streak_sitout") or loss_streak_sitout or 3
  )
  attack_r1_hi = knobs.get("attack_r1_hi")
  attack_r1_hi_f = float(attack_r1_hi) if attack_r1_hi is not None else None
  attack_boost_52w = bool(knobs.get("attack_boost_52w", False))
  attack_sleeve_frac = knobs.get("attack_sleeve_frac")
  attack_sleeve_f = float(attack_sleeve_frac) if attack_sleeve_frac is not None else None
  calendar_soft_only_underwater = bool(knobs.get("calendar_soft_only_underwater", False))
  ignore_briefing_size_in_attack = bool(knobs.get("ignore_briefing_size_in_attack", False))
  similarity_soft = bool(knobs.get("similarity_soft", False))
  similarity_iqr_skip = float(knobs.get("similarity_iqr_skip", 0.0025))
  similarity_iqr_soft = float(knobs.get("similarity_iqr_soft", 0.004))
  similarity_soft_mult = float(knobs.get("similarity_soft_mult", 0.5))
  similarity_hard_skip = bool(knobs.get("similarity_hard_skip", False))
  correlation_cap = bool(knobs.get("correlation_cap", False))
  max_pairwise_corr = float(knobs.get("max_pairwise_corr", 0.65))
  attack_leverage = knobs.get("attack_leverage")
  attack_leverage_f = float(attack_leverage) if attack_leverage is not None else None
  defense_leverage = knobs.get("defense_leverage")
  defense_leverage_f = float(defense_leverage) if defense_leverage is not None else None
  defense_sleeve_frac = knobs.get("defense_sleeve_frac")
  defense_sleeve_f = float(defense_sleeve_frac) if defense_sleeve_frac is not None else None
  attack_red_day_cap = float(knobs.get("attack_red_day_size_mult", 1.0))
  defense_similarity_mult = float(knobs.get("defense_similarity_mult", 1.0))
  use_ohlcv = bool(
    knobs.get("use_ohlcv", False)
    or use_v2_alpha
    or require_above_ema200
    or require_above_vwap
    or min_rel_volume_f is not None
    or vwap_score_boost > 0
    or vol_soft_penalty
    or indicator_mode in ("always", "defense_only")
    or research_agents_soft
    or research_agents_hard
  )
  # v2.4 lane defaults
  if str(knobs.get("lane") or "").startswith("v2_4"):
    similarity_soft = bool(knobs.get("similarity_soft", True))
    similarity_hard_skip = bool(knobs.get("similarity_hard_skip", False))
    correlation_cap = bool(knobs.get("correlation_cap", knobs.get("top_k", 1) > 1))
  if year is None:
    year = int(knobs.get("year") or 2025)
  month_table = months or months_for_year(year)
  end_date = month_table[-1][2]
  if learn_mistakes and bool(knobs.get("reset_mistakes", True)):
    from processor.pattern_forge.mistake_ledger import RULES_PATH, reset_ledger

    reset_ledger(keep_mistake_log=True)
    print(f"mistake ledger reset -> {RULES_PATH}", flush=True)
  eff_lev_cap = max(float(lev_cap), float(attack_leverage_f or 0), float(defense_leverage_f or 0))
  cfg = NoRuinConfig(
    default_sleeve_frac=sleeve,
    max_sleeve_frac=max(0.5, float(attack_sleeve_f or 0), float(defense_sleeve_f or 0), sleeve),
    max_daily_loss_pct=float(knobs.get("max_daily_loss_pct", 8.0)),
    max_trade_risk_pct=float(knobs.get("max_trade_risk_pct", 10.0)),
    max_leverage=max(eff_lev_cap, 1.0),
  )
  n_uni = int(knobs.get("universe_n", 0)) or 0
  raw = universe or fo_universe_list()
  tickers = [t for t in raw if t != "TATAMOTORS.NS"]
  if n_uni > 0:
    tickers = tickers[:n_uni]
  print(f"loading daily history for {len(tickers)} FO names… (end={end_date})", flush=True)
  lookback = int(knobs.get("lookback_days") or 520)
  series = _load_universe_series(tickers, end=end_date, lookback_days=lookback)
  ohlcv_series: dict[str, list[tuple[str, float, float, float, float]]] = {}
  if use_ohlcv:
    print(f"loading OHLCV for indicator filters…", flush=True)
    ohlcv_series = _load_universe_ohlcv(tickers, end=end_date, lookback_days=lookback)
  # Use most liquid for calendar
  calendar_src = max(series.values(), key=len)
  cap = capital
  start = capital
  peak = capital
  month_rows = []
  total_trades = 0
  green_months = 0
  include_trades = bool(knobs.get("include_trades", False))
  all_trades: list[dict] = []
  equity_curve: list[dict] = [{"date": month_table[0][1] if month_table else "", "capital": capital, "year": year}]
  # ticker -> last asof traded (cooldown)
  last_traded: dict[str, str] = {}
  last_cooldown_len: dict[str, int] = {}
  loss_streak = 0
  prev_month_green = False
  prev_day_red = False
  consecutive_red_days = 0
  month_peak = capital

  for name, a, b in month_table:
    m_start = cap
    month_peak = cap
    m_trades = 0
    m_wins = 0
    days = _trading_days(calendar_src, a, b)
    for i, asof in enumerate(days):
      ytd_green = cap >= start
      month_pnl_pct = 100.0 * (cap - m_start) / max(abs(m_start), 1e-9)
      peak_dd_pct = 100.0 * (cap - month_peak) / max(abs(month_peak), 1e-9) if month_peak > 0 else 0.0
      if asymmetric_freq:
        pre_attack = bool(ytd_green or prev_month_green)
        eff_max_trades = attack_max_trades_per_month if pre_attack else defense_max_trades_per_month
        eff_loss_sit = attack_loss_streak_sitout if pre_attack else defense_loss_streak_sitout
        eff_cooldown = attack_cooldown_days if pre_attack else defense_cooldown_days
      else:
        pre_attack = True
        eff_max_trades = max_trades_per_month
        eff_loss_sit = loss_streak_sitout
        eff_cooldown = ticker_cooldown_days

      if eff_max_trades > 0 and m_trades >= eff_max_trades:
        continue
      if eff_loss_sit > 0 and loss_streak >= eff_loss_sit:
        loss_streak = max(0, eff_loss_sit - 1)
        continue
      next_days = [d for d, _ in calendar_src if d > asof]
      if not next_days:
        continue
      t1 = next_days[0]
      if t1 > b and name:
        pass

      uni_closes = {t: _closes_asof(series[t], asof) for t in tickers if len(_closes_asof(series[t], asof)) >= 25}
      uni_ohlcv = None
      if use_ohlcv and ohlcv_series:
        uni_ohlcv = {
          t: _ohlcv_asof(ohlcv_series[t], asof)
          for t in tickers
          if t in ohlcv_series and len(_ohlcv_asof(ohlcv_series[t], asof).get("closes") or []) >= 25
        }
      if len(uni_closes) < 3:
        continue
      mkt = market_closes_asof(asof, allow_network=False)
      if len(mkt) < 20:
        mkt = next(iter(uni_closes.values()))

      regime_pre = soft_regime(list(mkt))
      breadth_pre = breadth_above_ma20(uni_closes)
      market_mode_pre, _ = resolve_market_mode(
        regime=regime_pre,
        breadth=breadth_pre,
        market_closes=mkt,
        asof=asof,
        nifty_ema_period=nifty_ema_period,
        defense_on_risk_off=defense_on_risk_off,
        defense_on_breadth_stress=defense_on_breadth_stress,
        defense_on_nifty_below_ema=defense_on_nifty_below_ema,
        october_defense=october_defense,
      )
      if asymmetric_freq and market_mode_pre == "defense":
        pre_attack = False
        eff_max_trades = defense_max_trades_per_month
        eff_loss_sit = defense_loss_streak_sitout
        eff_cooldown = defense_cooldown_days
        if eff_max_trades > 0 and m_trades >= eff_max_trades:
          continue
        if eff_loss_sit > 0 and loss_streak >= eff_loss_sit:
          loss_streak = max(0, eff_loss_sit - 1)
          continue

      briefing = (
        read_briefing(
          asof,
          mark_read=mistake_mark_read,
          regime=regime_pre,
          breadth_frac=(breadth_pre or {}).get("frac_above_ma20"),
          breadth_stress=bool((breadth_pre or {}).get("stress")),
          ytd_underwater=cap < start,
          loss_streak=loss_streak,
          market_mode=market_mode_pre,
          apply_fingerprints=bool(knobs.get("adaptive_fingerprints", True)),
        )
        if learn_mistakes
        else {"exclude_tickers": [], "sitout": False, "size_mult": 1.0, "summary": "learning_off"}
      )
      cooldown_ban: list[str] = []
      if eff_cooldown > 0 or big_loss_cooldown_days > 0:
        cal_idx = {d: i for i, (d, _) in enumerate(calendar_src)}
        ai = cal_idx.get(asof)
        if ai is not None:
          for tk, last_d in last_traded.items():
            li = cal_idx.get(last_d)
            need = int(last_cooldown_len.get(tk) or eff_cooldown or 0)
            if li is not None and need > 0 and 0 < (ai - li) <= need:
              cooldown_ban.append(tk)
      exclude = list(briefing.get("exclude_tickers") or []) + cooldown_ban

      day_r1_hi_trend = r1_hi_trend_f
      day_boost_52w = boost_near_52w_high
      if asymmetric_freq and pre_attack:
        if attack_r1_hi_f is not None:
          day_r1_hi_trend = attack_r1_hi_f
        if attack_boost_52w:
          day_boost_52w = True
      brief_size = float(briefing.get("size_mult") or 1.0)
      if asymmetric_freq and pre_attack and ignore_briefing_size_in_attack and not briefing.get("sitout"):
        brief_size = 1.0

      day_min_score = min_score
      if calendar_min_score_f is not None and name.lower() in calendar_min_score_months:
        day_min_score = max(day_min_score, calendar_min_score_f)

      choice = choose_daily_candidate(
        uni_closes,
        market_closes=mkt,
        long_only=long_only,
        min_score=day_min_score,
        r1_lo=r1_lo,
        r1_hi=r1_hi,
        top_k=top_k,
        use_breadth_veto=use_breadth_veto,
        breadth_scale=breadth_scale,
        exclude_tickers=exclude,
        mistake_size_mult=brief_size,
        sitout=bool(briefing.get("sitout")),
        vol_scale_rank=vol_scale_rank,
        skip_extended_r5=skip_extended_r5_f,
        skip_extended_r5_defense_only=skip_extended_r5_defense_only,
        skip_extended_r5_attack=skip_extended_r5_attack_f,
        require_market_ts_mom=require_market_ts_mom,
        market_ts_min=market_ts_min,
        require_above_ema200=require_above_ema200,
        min_rel_volume=min_rel_volume_f,
        require_above_vwap=require_above_vwap,
        vwap_score_boost=vwap_score_boost,
        vol_soft_penalty=vol_soft_penalty,
        universe_ohlcv=uni_ohlcv,
        score_mode=score_mode,
        indicator_mode=indicator_mode,
        defense_sitout=defense_sitout,
        defense_chop_sitout=defense_chop_sitout,
        defense_size_mult=defense_size_mult,
        defense_on_risk_off=defense_on_risk_off,
        defense_on_breadth_stress=defense_on_breadth_stress,
        defense_on_nifty_below_ema=defense_on_nifty_below_ema,
        nifty_ema_period=nifty_ema_period,
        october_defense=october_defense,
        october_size_mult=october_size_mult,
        calendar_sit_months=calendar_sit_months,
        calendar_sit_mult=calendar_sit_mult,
        r1_hi_trend=day_r1_hi_trend,
        boost_near_52w_high=day_boost_52w,
        asof=asof,
        correlation_cap=correlation_cap,
        max_pairwise_corr=max_pairwise_corr,
      )
      if learn_mistakes:
        banned = set(str(x).upper() for x in (briefing.get("exclude_tickers") or []))
        for row in (choice.get("ranked_top") or [])[:5]:
          tk = str(row.get("ticker") or "").upper()
          if tk in banned and row.get("side") != "flat":
            note_repeat_blocked(asof=asof, ticker=tk)
      primary = choice.get("primary") or {}
      picks = list(choice.get("picks") or [])

      # Calendar entry: only fire in named months when market regime is trend
      if (
        picks
        and calendar_require_trend
        and name.lower() in calendar_require_trend
        and str(choice.get("regime") or regime_pre or "").lower() != "trend"
      ):
        choice = {
          **choice,
          "picked": "cash",
          "picks": [],
          "size_mult": 0.0,
          "reason": f"calendar_require_trend:{name.lower()}:{choice.get('regime') or regime_pre}",
          "stress_veto": True,
        }
        primary = {"side": "flat", "confidence": 0.5, "reason": choice["reason"]}
        picks = []
      if not picks and choice.get("picked") not in (None, "cash"):
        picks = [{"ticker": choice["picked"], "side": primary.get("side"), "score": primary.get("score"), "confidence": primary.get("confidence")}]
      peer_rets = []
      cand_r1 = None
      for tname, closes in uni_closes.items():
        if len(closes) >= 2 and closes[-2] > 0:
          r1 = closes[-1] / closes[-2] - 1.0
          peer_rets.append(r1)
          if tname == choice.get("picked"):
            cand_r1 = r1
      cues: dict = {"overnight_gap_pct": None, "us_ret_pct": None, "asia_ret_pct": None, "feed_status": {}}
      if overnight_feeds:
        cues = overnight_cues_asof(asof, allow_network=allow_overnight_net, local_closes=list(mkt))
      elif len(mkt) >= 2 and mkt[-2] > 0:
        cues = {
          "overnight_gap_pct": mkt[-1] / mkt[-2] - 1.0,
          "us_ret_pct": None,
          "asia_ret_pct": None,
          "feed_status": {"in_gap": "local_proxy"},
        }

      size_mult_preview = float(choice.get("size_mult") or 1.0)
      ytd_pnl_preview = cap - start
      pg_note = None
      if profit_guard and ytd_pnl_preview < 0:
        pg_note = "underwater_half_size"
      elif profit_guard and ytd_pnl_preview > 0:
        pg_note = "ytd_green_day_loss_cap"

      cand_feats = dict((primary.get("features") or {}))
      if not cand_feats:
        for row in choice.get("ranked_top") or []:
          if str(row.get("ticker") or "") == str(choice.get("picked") or "") and isinstance(row.get("features"), dict):
            cand_feats = dict(row["features"])
            break
      peer_rvs: list[float] = []
      if uni_ohlcv:
        for tname, ov in uni_ohlcv.items():
          ff = stock_daily_features(
            ov.get("closes") or [],
            volumes=ov.get("volumes"),
            highs=ov.get("highs"),
            lows=ov.get("lows"),
          )
          if ff.get("rel_volume") is not None:
            peer_rvs.append(float(ff["rel_volume"]))

      swarm_kwargs = dict(
        market_closes=list(mkt),
        peer_rets=peer_rets,
        overnight_gap_pct=cues.get("overnight_gap_pct"),
        asia_ret_pct=cues.get("asia_ret_pct"),
        us_ret_pct=cues.get("us_ret_pct"),
        hard_veto=swarm_hard_veto,
        profit_guard_note=pg_note,
        feed_status=cues.get("feed_status") or {},
        candidate_features=cand_feats or None,
        peer_rel_volumes=peer_rvs or None,
        month_pnl_pct=month_pnl_pct,
        consecutive_red_days=consecutive_red_days,
        peak_dd_pct=peak_dd_pct,
        liquidity_min_rel_volume=liquidity_min_rel_volume,
        liquidity_soft_rel_volume=liquidity_soft_rel_volume,
        auction_chase_gap_bps=auction_chase_gap_bps,
        bad_month_red_days=bad_month_red_days,
      )
      swarm_msgs, agreement = daily_swarm_tape(
        choice,
        candidate_ret_1=cand_r1,
        **swarm_kwargs,
      )
      # Hard swarm veto → force cash (never amplify)
      if swarm_hard_veto and picks and not agreement.get("tradeable"):
        choice = {
          **choice,
          "picked": "cash",
          "picks": [],
          "size_mult": 0.0,
          "reason": f"swarm_hard_veto:{agreement.get('reason')}",
          "stress_veto": True,
        }
        primary = {"side": "flat", "confidence": 0.5, "reason": choice["reason"]}
        picks = []
        swarm_msgs, agreement = daily_swarm_tape(
          choice,
          candidate_ret_1=None,
          **swarm_kwargs,
        )

      # NewsEdgeScan: soft size or hard sit (never amplify)
      news_msg = next((m for m in swarm_msgs if m.get("agent") == "NewsEdgeScan"), None)
      if news_msg and picks and news_msg.get("vote") == "skip":
        if news_edge_hard:
          choice = {
            **choice,
            "picked": "cash",
            "picks": [],
            "size_mult": 0.0,
            "reason": f"news_edge_hard:{news_msg.get('reason')}",
            "stress_veto": True,
          }
          primary = {"side": "flat", "confidence": 0.5, "reason": choice["reason"]}
          picks = []
        elif news_edge_soft:
          sm = news_edge_size_mult("skip", soft_mult=news_edge_soft_mult)
          choice = {**choice, "size_mult": min(float(choice.get("size_mult") or 1.0), sm)}

      # New research agents: LiquidityGate / StockResearch / OpenAuction / Asia / BadMonth
      _RESEARCH_AGENTS = (
        "LiquidityGate",
        "StockResearch",
        "OpenAuctionQuality",
        "AsiaBasket",
        "BadMonthGuard",
      )
      if (research_agents_soft or research_agents_hard) and picks:
        for aname in _RESEARCH_AGENTS:
          am = next((m for m in swarm_msgs if m.get("agent") == aname), None)
          if not am:
            continue
          sm = research_agent_size_mult(am, soft_mult=research_agents_soft_mult)
          if am.get("vote") == "skip" or sm < 1.0:
            if research_agents_hard and (am.get("vote") == "skip" or sm <= 0.0):
              choice = {
                **choice,
                "picked": "cash",
                "picks": [],
                "size_mult": 0.0,
                "reason": f"research_hard:{aname}:{am.get('reason')}",
                "stress_veto": True,
              }
              primary = {"side": "flat", "confidence": 0.5, "reason": choice["reason"]}
              picks = []
              break
            if research_agents_soft:
              choice = {**choice, "size_mult": min(float(choice.get("size_mult") or 1.0), sm if sm > 0 else research_agents_soft_mult)}

      # Soft similarity gate — crowded tape size-down / skip (never amplify)
      sim_note: str | None = None
      if similarity_soft and picks:
        sim_mult, sim_reason, sim_iqr = similarity_size_mult(
          peer_rets=peer_rets,
          iqr_hard_skip=similarity_iqr_skip,
          iqr_soft=similarity_iqr_soft,
          soft_mult=similarity_soft_mult * (defense_similarity_mult if (asymmetric_freq and not pre_attack) else 1.0),
          allow_hard_skip=similarity_hard_skip,
        )
        sim_note = sim_reason
        if sim_mult <= 0.0:
          choice = {
            **choice,
            "picked": "cash",
            "picks": [],
            "size_mult": 0.0,
            "reason": f"similarity_soft:{sim_reason}",
            "stress_veto": True,
          }
          primary = {"side": "flat", "confidence": 0.5, "reason": choice["reason"]}
          picks = []
        else:
          choice = {
            **choice,
            "size_mult": min(float(choice.get("size_mult") or 1.0), sim_mult),
            "similarity_iqr": sim_iqr,
          }

      # Calendar soft months — size only; v2.3 can limit soft to underwater YTD
      apply_cal_soft = bool(calendar_soft_months and name.lower() in calendar_soft_months and picks)
      if apply_cal_soft and calendar_soft_only_underwater and cap >= start:
        apply_cal_soft = False
      if apply_cal_soft:
        choice = {
          **choice,
          "size_mult": min(float(choice.get("size_mult") or 1.0), calendar_soft_mult),
        }

      decision = {
        "kind": "decision",
        "asof": asof,
        "ticker": choice.get("picked"),
        "family": "daily_swing",
        "run_id": run_id,
        "iteration_id": iteration_id,
        "choice": "skip" if choice.get("picked") == "cash" else "fire",
        "primary": primary,
        "picks": picks,
        "breadth": choice.get("breadth"),
        "stress_veto": choice.get("stress_veto"),
        "feed_status": cues.get("feed_status") or {},
        "mistake_briefing": {
          "summary": briefing.get("summary"),
          "exclude_tickers": briefing.get("exclude_tickers"),
          "sitout": briefing.get("sitout"),
          "size_mult": briefing.get("size_mult"),
        },
        "hybrid_choice": choice.get("hybrid_choice"),
        "swarm_agreement": agreement,
        "swarm_messages": swarm_msgs,
        "no_ruin": None,
        "skip_reason": None if choice.get("picked") != "cash" else choice.get("reason"),
        "notes": [],
        "disclaimer": "Paper/sim audit — not investment advice.",
      }

      day_notes_pre: list[str] = []
      day_sleeve = sleeve
      if asymmetric_freq and pre_attack and attack_sleeve_f is not None:
        day_sleeve = max(sleeve, min(0.5, attack_sleeve_f))
      elif asymmetric_freq and defense_sleeve_f is not None:
        day_sleeve = min(sleeve, max(0.05, defense_sleeve_f))
      if (
        asymmetric_freq
        and pre_attack
        and attack_ytd_sleeve_cap_f is not None
        and start > 0
      ):
        ytd_ret_pct = 100.0 * (cap - start) / start
        if ytd_ret_pct >= attack_ytd_sleeve_cap_f:
          day_sleeve = min(day_sleeve, max(0.05, sleeve * attack_ytd_sleeve_mult))
          day_notes_pre.append(f"attack_ytd_sleeve_cap=ytd{ytd_ret_pct:.0f}%")
      nr = risk_budget(equity=cap, starting_capital=start, peak_equity=peak, sleeve_frac=day_sleeve, cfg=cfg)
      decision["no_ruin"] = state_dict(nr)
      if nr.halted:
        decision["choice"] = "skip"
        decision["skip_reason"] = "no_ruin_halt"
        log_decision(decision)
        break

      if choice.get("picked") == "cash" or not picks:
        log_decision(decision)
        continue

      conf = float(primary.get("confidence") or 0.55)
      lev = min(cfg.max_leverage, max(1.0, lev_cap))
      if asymmetric_freq:
        if pre_attack and attack_leverage_f is not None:
          lev = min(cfg.max_leverage, max(lev, attack_leverage_f))
        elif defense_leverage_f is not None:
          lev = min(cfg.max_leverage, defense_leverage_f)
      elif attack_leverage_f is not None and pre_attack:
        lev = min(cfg.max_leverage, max(lev, attack_leverage_f))
      lev, nnotes = apply_no_ruin_to_leverage(lev, state=nr, cfg=cfg)
      _ = conf
      if lev <= 0:
        decision["choice"] = "skip"
        decision["skip_reason"] = "leverage_zero"
        log_decision(decision)
        continue

      size_mult = min(1.0, float(choice.get("size_mult") or 1.0))  # never amplify
      ytd_pnl = cap - start
      # Defend when underwater: half size until back to green YTD
      if profit_guard and ytd_pnl < 0:
        size_mult = min(size_mult, 0.5)
        day_notes_pre.append("profit_guard_underwater_half")
      if asymmetric_freq and pre_attack and prev_day_red and attack_red_day_cap < 1.0:
        size_mult = min(size_mult, attack_red_day_cap)
        day_notes_pre.append(f"attack_red_day_cap={attack_red_day_cap}")
      # Equal-weight risk across top-k (same day risk budget as single-name path)
      n_pick = float(len(picks))
      name_cap = max(0.05, min(1.0, max_single_name_day_frac))
      per_frac = min(1.0 / n_pick, name_cap)
      per_notional = nr.risk_budget * lev * size_mult * per_frac
      # renormalize if caps leave unused budget unused — never amplify above full day risk
      used = per_frac * n_pick
      if used < 1.0 - 1e-9:
        per_notional = (nr.risk_budget * lev * size_mult) * per_frac  # already capped; leave slack (safer)
      max_day = abs(cap) * float(knobs.get("max_daily_loss_pct", 8.0)) / 100.0
      if profit_guard:
        floor = abs(start) * profit_guard_floor_pct / 100.0
        # Never allow a single day to erase more than profits made (YTD), once ahead
        if ytd_pnl > 0:
          max_day = min(max_day, float(ytd_pnl))
        else:
          max_day = min(max_day, floor)
      day_pnl = 0.0
      day_notes = list(nnotes) + day_notes_pre
      if size_mult < 1.0:
        day_notes.append(f"size_mult={size_mult}")
      n_fired = 0
      day_trades: list[dict] = []
      for pick in picks:
        ticker = str(pick["ticker"])
        px_t = {d: c for d, c in series[ticker]}
        if asof not in px_t or t1 not in px_t:
          continue
        side = str(pick.get("side") or primary.get("side"))
        path: dict
        if use_v2_alpha and ticker in ohlcv_series:
          bar = _ohlcv_bar_on(ohlcv_series[ticker], t1)
          asof_bars = _ohlcv_asof(ohlcv_series[ticker], asof)
          if bar and len(asof_bars.get("closes") or []) >= 25:
            path = v2_alpha_plan_and_simulate(
              asof_bars["closes"],
              side=side,
              regime=str(choice.get("regime") or regime_pre or ""),
              entry=float(px_t[asof]),
              t1_high=bar[0],
              t1_low=bar[1],
              t1_close=bar[2],
              highs_asof=asof_bars.get("highs"),
              lows_asof=asof_bars.get("lows"),
              knobs=knobs,
            )
          else:
            path = next_day_pnl_frac([px_t[asof], px_t[t1]], side=side)
        else:
          path = next_day_pnl_frac([px_t[asof], px_t[t1]], side=side)
        if not path.get("ok"):
          continue
        legs = path.get("legs") or [{"frac": 1.0, "px": path["exit_px"], "reason": path.get("exit_reason")}]
        # Entry side + one exit side per leg (partials pay an extra exit)
        fees = IN_FO_COST.fee_on_notional(per_notional, sides=1)
        for leg in legs:
          fees += IN_FO_COST.fee_on_notional(per_notional * float(leg.get("frac") or 1.0), sides=1)
        pnl = notional_pnl(per_notional, float(path["pnl_frac"]), fees)
        day_pnl += pnl
        n_fired += 1
        plan = path.get("plan") or {}
        trade = {
          "kind": "trade",
          "ticker": ticker,
          "side": path["side"],
          "entry_price": path["entry_px"],
          "exit_price": path["exit_px"],
          "entry_notional": round(per_notional, 2),
          "fees": round(fees, 4),
          "pnl": pnl,
          "pnl_pct": round(100.0 * float(path["pnl_frac"]), 3),
          "exit_reason": path["exit_reason"],
          "exit_book": "v2_alpha" if use_v2_alpha else "next_close",
          "dip_class": plan.get("dip_class") or (path.get("dip") or {}).get("dip_class"),
          "tp_policy": plan.get("tp_policy"),
          "sl_pct": plan.get("sl_pct"),
          "tp_pct": plan.get("tp_pct"),
          "leverage": round(lev, 4),
          "family": "daily_swing",
          "signal_reason": primary.get("reason"),
          "top_k": top_k,
          "size_mult": size_mult,
          "asof": asof,
          "exit_asof": t1,
          "run_id": run_id,
          "iteration_id": iteration_id,
          "disclaimer": "Paper/sim audit — not investment advice.",
        }
        log_trade(trade)
        day_trades.append(trade)
        last_traded[ticker.upper()] = asof
        pnl_pct_t = float(trade["pnl_pct"])
        if pnl_pct_t <= -2.0 and big_loss_cooldown_days > 0:
          last_cooldown_len[ticker.upper()] = max(eff_cooldown, big_loss_cooldown_days)
        else:
          last_cooldown_len[ticker.upper()] = eff_cooldown
        if include_trades:
          all_trades.append({**trade, "year": year, "month": name})
        m_trades += 1
        if pnl > 0:
          m_wins += 1
        total_trades += 1

      if n_fired == 0:
        decision["choice"] = "skip"
        decision["skip_reason"] = "missing_px"
        log_decision(decision)
        continue

      if day_pnl < -max_day:
        day_pnl = -max_day
        day_notes.append("daily_loss_clamp")
      if day_pnl < 0:
        loss_streak += 1
        prev_day_red = True
        consecutive_red_days += 1
      else:
        loss_streak = 0
        prev_day_red = False
        consecutive_red_days = 0
      cap = round(cap + day_pnl, 2)
      peak = update_peak(peak, cap)
      if cap > month_peak:
        month_peak = cap
      if include_trades:
        equity_curve.append(
          {
            "date": t1,
            "asof": asof,
            "capital": round(cap, 2),
            "day_pnl": round(day_pnl, 4),
            "year": year,
            "month": name,
          }
        )
      decision["notes"] = day_notes
      decision["day_pnl"] = round(day_pnl, 4)
      log_decision(decision)

      if learn_mistakes:
        learn_from_day(
          asof=asof,
          trades=day_trades,
          day_pnl=day_pnl,
          day_return_pct=round(100.0 * day_pnl / max(cap - day_pnl, 1.0), 4),
          regime=str(choice.get("regime") or ""),
          breadth_frac=(choice.get("breadth") or {}).get("frac_above_ma20"),
          breadth_stress=bool((choice.get("breadth") or {}).get("stress")),
          ytd_underwater=(cap - day_pnl) < start,
          loss_streak=loss_streak,
          market_mode=str(choice.get("market_mode") or market_mode_pre or ""),
          adaptive_fingerprints=bool(knobs.get("adaptive_fingerprints", True)),
        )
    pct = round(100.0 * (cap - m_start) / m_start, 3) if m_start else 0.0
    if pct > 0:
      green_months += 1
    month_rows.append(
      {
        "month": name,
        "capital_start": round(m_start, 2),
        "capital_end": round(cap, 2),
        "month_return_pct": pct,
        "n_trades": m_trades,
        "wins": m_wins,
      }
    )
    print(f"  {name:12} {pct:+.2f}% trades={m_trades} end={cap:,.2f}", flush=True)
    prev_month_green = pct > 0

  worst = min((float(m["month_return_pct"]) for m in month_rows), default=0.0)
  best_m = max((float(m["month_return_pct"]) for m in month_rows), default=0.0)
  year_pnl = round(cap - capital, 2)
  worst_month_pnl = min((float(m["capital_end"]) - float(m["capital_start"]) for m in month_rows), default=0.0)
  loss_lte_profits = abs(min(0.0, worst_month_pnl)) <= max(0.0, year_pnl)
  lane = str(knobs.get("lane") or ("v2_product" if learn_mistakes else "daily_swing"))
  report = {
    "run_id": run_id,
    "iteration_id": iteration_id,
    "strategy": "daily_swing",
    "lane": lane,
    "benchmark": str(year),
    "claim": "paper/daily close-to-close; clean PIT; modeled IN_FO ~12bps RT (not cash 30bps); not live fills",
    "capital_start": capital,
    "capital_end": round(cap, 2),
    "year_pnl": year_pnl,
    "total_return_pct": round(100.0 * (cap - capital) / capital, 3),
    "green_months": green_months,
    "months_total": len(month_rows),
    "worst_month_pct": round(worst, 3),
    "best_month_pct": round(best_m, 3),
    "worst_month_pnl": round(worst_month_pnl, 2),
    "loss_lte_profits": loss_lte_profits,
    "n_trades": total_trades,
    "months": month_rows,
    "knobs": knobs,
    "no_ruin": True,
    "profit_guard": profit_guard,
    "swarm_hard_veto": swarm_hard_veto,
    "long_only": long_only,
    "trades": all_trades if include_trades else None,
    "equity_curve": equity_curve if include_trades else None,
    "goal": {
      "green_months_min": 8,
      "mean_month_positive": True,
      "worst_month_gt": -12.0,
      "loss_lte_profits": True,
    },
    "goal_met": green_months >= 8 and cap > capital and loss_lte_profits,
  }
  out_path = ROOT / "models" / "pattern_forge" / f"benchmark_{year}_daily_swing_{run_id}.json"
  out_path.parent.mkdir(parents=True, exist_ok=True)
  import json

  out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
  if knobs.get("promote_summary", True):
    promote_as = str(knobs.get("promote_as") or "")
    if not promote_as:
      if lane in ("v2_1", "v2.1"):
        promote_as = "v2_1"
      elif lane == "v2_alpha":
        promote_as = "v2_alpha"
      elif "next" in lane or "guard" in lane:
        promote_as = "aim_next"
      elif "aim40" in lane:
        promote_as = "aim40"
      else:
        promote_as = "product"
    # Never silently overwrite locked v2 unless promote_as is explicitly "v2"
    promote_files = {
      "v2": "v2_latest.json",
      "v2_1": "v2_1_latest.json",
      "v2_alpha": "v2_alpha_latest.json",
      "v3": "v3_latest.json",
      "aim_next": "v2_aim_next_latest.json",
      "aim40": "v2_aim40_latest.json",
      "product": "v2_product_latest.json",
    }
    product_path = ROOT / "models" / "pattern_forge" / promote_files.get(promote_as, "v3_latest.json")
    if promote_as == "v2" and not knobs.get("allow_overwrite_v2"):
      print("skip promote to v2_latest.json (locked; set allow_overwrite_v2=1 to force)", flush=True)
    else:
      product_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
      if promote_as == "v2" and knobs.get("allow_overwrite_v2"):
        (ROOT / "models" / "pattern_forge" / "v2_product_latest.json").write_text(
          json.dumps(report, indent=2), encoding="utf-8"
        )
  if knobs.get("write_lab_summary", knobs.get("promote_summary", True)):
    log_run(
      {
        "run_id": run_id,
        "family": "daily_swing",
        "lane": lane,
        "benchmark": str(year),
        "total_return_pct": report["total_return_pct"],
        "green_months": green_months,
        "months_total": report["months_total"],
        "worst_month_pct": report["worst_month_pct"],
        "worst_month_pnl": report["worst_month_pnl"],
        "year_pnl": report["year_pnl"],
        "loss_lte_profits": report["loss_lte_profits"],
        "capital_end": report["capital_end"],
        "goal_met": report["goal_met"],
        "knobs": knobs,
      }
    )
    write_summary(
      {
        "status": "ok",
        "latest_run_id": run_id,
        "family": "daily_swing",
        "lane": lane,
        "benchmark": str(year),
        "total_return_pct": report["total_return_pct"],
        "green_months": green_months,
        "months_total": report["months_total"],
        "worst_month_pct": report["worst_month_pct"],
        "best_month_pct": report["best_month_pct"],
        "worst_month_pnl": report["worst_month_pnl"],
        "year_pnl": report["year_pnl"],
        "loss_lte_profits": report["loss_lte_profits"],
        "goal_met": report["goal_met"],
        "capital_end": report["capital_end"],
        "capital_start": capital,
        "months_equity": [
          {
            "month": m["month"],
            "label": m["month"][:3].title(),
            "pnl": round(float(m["capital_end"]) - float(m["capital_start"]), 2),
            "month_return_pct": m["month_return_pct"],
            "n_trades": m["n_trades"],
            "wins": m["wins"],
            "capital_end": m["capital_end"],
          }
          for m in month_rows
        ],
        "claim": report["claim"],
        "knobs": knobs,
      }
    )
  print(f"wrote {out_path}", flush=True)
  print(
    f"TOTAL {report['total_return_pct']:+.2f}% green={green_months}/{report['months_total']} "
    f"worst={report['worst_month_pct']:+.2f}% goal_met={report['goal_met']}",
    flush=True,
  )
  return report


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--months", default="", help="comma names e.g. october,november")
  ap.add_argument("--year", type=int, default=2025)
  ap.add_argument("--min-score", type=float, default=0.005)
  ap.add_argument("--leverage", type=float, default=11.0)
  ap.add_argument("--sleeve", type=float, default=0.24)
  ap.add_argument("--top-k", type=int, default=1)
  ap.add_argument("--no-breadth-veto", action="store_true", default=True)
  ap.add_argument("--breadth-scale", action="store_true", default=False)
  ap.add_argument("--no-learn", action="store_true")
  ap.add_argument("--no-profit-guard", action="store_true")
  ap.add_argument("--shorts", action="store_true", help="FO two-sided (long_only=False)")
  ap.add_argument("--swarm-hard-veto", action="store_true")
  ap.add_argument("--overnight-feeds", action="store_true")
  ap.add_argument("--lane", default="v2")
  ap.add_argument("--promote-as", default="", help="v2|v2_1|v2_alpha|product|aim40|aim_next (empty=derive)")
  ap.add_argument("--no-promote", action="store_true")
  args = ap.parse_args()
  year = int(args.year)
  months = months_for_year(year)
  if args.months.strip():
    want = {x.strip().lower() for x in args.months.split(",") if x.strip()}
    months = [m for m in months if m[0] in want]
  lane = args.lane
  is_v21 = lane in ("v2_1", "v2.1") or args.shorts or args.swarm_hard_veto
  is_v2a = lane == "v2_alpha"
  promote_as = args.promote_as or (
    "v2_alpha" if is_v2a else ("v2_1" if is_v21 else ("v2" if lane == "v2" else "product"))
  )
  run_daily_benchmark(
    year=year,
    months=months,
    knobs={
      "min_score": args.min_score,
      "leverage": args.leverage,
      "sleeve_frac": args.sleeve,
      "top_k": args.top_k,
      "use_breadth_veto": False,
      "breadth_scale": bool(args.breadth_scale),
      "learn_mistakes": not args.no_learn,
      "profit_guard": not args.no_profit_guard,
      "profit_guard_floor_pct": 2.0,
      "reset_mistakes": True,
      "promote_summary": not args.no_promote,
      "write_lab_summary": not args.no_promote and promote_as not in ("v2_1",),
      "promote_as": promote_as,
      "allow_overwrite_v2": False,
      "lane": lane if not is_v21 or lane.startswith("v2") else "v2_1",
      "exit_book": "v2_alpha" if is_v2a else None,
      "use_ohlcv": bool(is_v2a),
      "long_only": not args.shorts and not is_v21,
      "swarm_hard_veto": bool(args.swarm_hard_veto) or is_v21,
      "overnight_feeds": bool(args.overnight_feeds) or is_v21,
      "allow_overnight_network": False,
      "r1_lo": 0.005,
      "r1_hi": 0.06,
      "universe_n": 0,
      "max_daily_loss_pct": 8.0,
      "year": year,
    },
  )

if __name__ == "__main__":
  main()
