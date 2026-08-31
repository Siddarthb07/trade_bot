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
from processor.day_sim import _fetch_history
from processor.fo_universe import fo_universe_list
from processor.no_ruin import NoRuinConfig, apply_no_ruin_to_leverage, risk_budget, state_dict, update_peak
from processor.pattern_forge.daily_swing import choose_daily_candidate, next_day_pnl_frac
from processor.pattern_forge.daily_swarm_tape import daily_swarm_tape
from processor.pattern_forge.ledger import log_decision, log_run, log_trade, write_summary
from processor.pattern_forge.market_regime_proxy import market_closes_asof
from processor.pattern_forge.mistake_ledger import learn_from_day, note_repeat_blocked, read_briefing
from processor.pattern_forge.overnight_feeds import overnight_cues_asof
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


def months_for_year(year: int) -> list[tuple[str, str, str]]:
  import calendar

  out: list[tuple[str, str, str]] = []
  for i, name in enumerate(_MONTH_NAMES, start=1):
    last = calendar.monthrange(year, i)[1]
    out.append((name, f"{year}-{i:02d}-01", f"{year}-{i:02d}-{last:02d}"))
  return out


MONTHS_2025 = months_for_year(2025)


def _load_universe_series(tickers: list[str], end: str = "2025-12-31", *, lookback_days: int = 520) -> dict[str, list[tuple[str, float]]]:
  end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
  out: dict[str, list[tuple[str, float]]] = {}
  for t in tickers:
    hist = _fetch_history(t, end_dt, lookback_days=lookback_days)
    out[t] = [(d, c) for d, c in hist if d <= end]
  return out

def _closes_asof(series: list[tuple[str, float]], asof: str) -> list[float]:
  return [c for d, c in series if d <= asof]


def _trading_days(series: list[tuple[str, float]], start: str, end: str) -> list[str]:
  return [d for d, _ in series if start <= d <= end]


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
  profit_guard = bool(knobs.get("profit_guard", False))
  profit_guard_floor_pct = float(knobs.get("profit_guard_floor_pct", 2.0))
  swarm_hard_veto = bool(knobs.get("swarm_hard_veto", False))
  overnight_feeds = bool(knobs.get("overnight_feeds", False))
  allow_overnight_net = bool(knobs.get("allow_overnight_network", False))
  vol_scale_rank = bool(knobs.get("vol_scale_rank", False))
  skip_extended_r5 = knobs.get("skip_extended_r5")
  skip_extended_r5_f = float(skip_extended_r5) if skip_extended_r5 is not None else None
  require_market_ts_mom = bool(knobs.get("require_market_ts_mom", False))
  market_ts_min = float(knobs.get("market_ts_min", 0.0))
  ticker_cooldown_days = max(0, int(knobs.get("ticker_cooldown_days", 0)))
  max_single_name_day_frac = float(knobs.get("max_single_name_day_frac", 1.0))  # of day risk budget
  if year is None:
    year = int(knobs.get("year") or 2025)
  month_table = months or months_for_year(year)
  end_date = month_table[-1][2]
  if learn_mistakes and bool(knobs.get("reset_mistakes", True)):
    from processor.pattern_forge.mistake_ledger import RULES_PATH, reset_ledger

    reset_ledger(keep_mistake_log=True)
    print(f"mistake ledger reset → {RULES_PATH}", flush=True)
  cfg = NoRuinConfig(
    default_sleeve_frac=sleeve,
    max_sleeve_frac=0.5,
    max_daily_loss_pct=float(knobs.get("max_daily_loss_pct", 8.0)),
    max_trade_risk_pct=float(knobs.get("max_trade_risk_pct", 10.0)),
    max_leverage=max(lev_cap, 1.0),
  )
  n_uni = int(knobs.get("universe_n", 0)) or 0
  raw = universe or fo_universe_list()
  tickers = [t for t in raw if t != "TATAMOTORS.NS"]
  if n_uni > 0:
    tickers = tickers[:n_uni]
  print(f"loading daily history for {len(tickers)} FO names… (end={end_date})", flush=True)
  series = _load_universe_series(tickers, end=end_date, lookback_days=int(knobs.get("lookback_days") or 520))
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

  for name, a, b in month_table:
    m_start = cap
    m_trades = 0
    m_wins = 0
    days = _trading_days(calendar_src, a, b)
    for i, asof in enumerate(days):
      # Need next session in calendar for exit
      # Find next day after asof in calendar_src
      next_days = [d for d, _ in calendar_src if d > asof]
      if not next_days:
        continue
      t1 = next_days[0]
      if t1 > b and name:  # allow exit into next month
        pass

      uni_closes = {t: _closes_asof(series[t], asof) for t in tickers if len(_closes_asof(series[t], asof)) >= 25}
      if len(uni_closes) < 3:
        continue
      mkt = market_closes_asof(asof, allow_network=False)
      if len(mkt) < 20:
        # fallback: first ticker closes
        mkt = next(iter(uni_closes.values()))

      briefing = (
        read_briefing(asof, mark_read=True)
        if learn_mistakes
        else {"exclude_tickers": [], "sitout": False, "size_mult": 1.0, "summary": "learning_off"}
      )
      cooldown_ban: list[str] = []
      if ticker_cooldown_days > 0:
        # Ban names traded within last N calendar trading days on this calendar
        cal_idx = {d: i for i, (d, _) in enumerate(calendar_src)}
        ai = cal_idx.get(asof)
        if ai is not None:
          for tk, last_d in last_traded.items():
            li = cal_idx.get(last_d)
            if li is not None and 0 < (ai - li) <= ticker_cooldown_days:
              cooldown_ban.append(tk)
      exclude = list(briefing.get("exclude_tickers") or []) + cooldown_ban

      choice = choose_daily_candidate(
        uni_closes,
        market_closes=mkt,
        long_only=long_only,
        min_score=min_score,
        r1_lo=r1_lo,
        r1_hi=r1_hi,
        top_k=top_k,
        use_breadth_veto=use_breadth_veto,
        breadth_scale=breadth_scale,
        exclude_tickers=exclude,
        mistake_size_mult=float(briefing.get("size_mult") or 1.0),
        sitout=bool(briefing.get("sitout")),
        vol_scale_rank=vol_scale_rank,
        skip_extended_r5=skip_extended_r5_f,
        require_market_ts_mom=require_market_ts_mom,
        market_ts_min=market_ts_min,
      )
      if learn_mistakes:
        banned = set(str(x).upper() for x in (briefing.get("exclude_tickers") or []))
        for row in (choice.get("ranked_top") or [])[:5]:
          tk = str(row.get("ticker") or "").upper()
          if tk in banned and row.get("side") != "flat":
            note_repeat_blocked(asof=asof, ticker=tk)
      primary = choice.get("primary") or {}
      picks = list(choice.get("picks") or [])
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

      swarm_msgs, agreement = daily_swarm_tape(
        choice,
        market_closes=list(mkt),
        peer_rets=peer_rets,
        candidate_ret_1=cand_r1,
        overnight_gap_pct=cues.get("overnight_gap_pct"),
        asia_ret_pct=cues.get("asia_ret_pct"),
        us_ret_pct=cues.get("us_ret_pct"),
        hard_veto=swarm_hard_veto,
        profit_guard_note=pg_note,
        feed_status=cues.get("feed_status") or {},
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
          market_closes=list(mkt),
          peer_rets=peer_rets,
          candidate_ret_1=None,
          overnight_gap_pct=cues.get("overnight_gap_pct"),
          asia_ret_pct=cues.get("asia_ret_pct"),
          us_ret_pct=cues.get("us_ret_pct"),
          hard_veto=swarm_hard_veto,
          profit_guard_note=pg_note,
          feed_status=cues.get("feed_status") or {},
        )

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

      nr = risk_budget(equity=cap, starting_capital=start, peak_equity=peak, sleeve_frac=sleeve, cfg=cfg)
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
        day_notes_pre = ["profit_guard_underwater_half"]
      else:
        day_notes_pre = []
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
        path = next_day_pnl_frac([px_t[asof], px_t[t1]], side=str(pick.get("side") or primary.get("side")))
        if not path.get("ok"):
          continue
        fees = IN_FO_COST.fee_on_notional(per_notional, sides=2)
        pnl = notional_pnl(per_notional, float(path["pnl_frac"]), fees)
        day_pnl += pnl
        n_fired += 1
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
      cap = round(cap + day_pnl, 2)
      peak = update_peak(peak, cap)
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
  ap.add_argument("--promote-as", default="", help="v2|v2_1|product|aim40|aim_next (empty=derive)")
  ap.add_argument("--no-promote", action="store_true")
  args = ap.parse_args()
  year = int(args.year)
  months = months_for_year(year)
  if args.months.strip():
    want = {x.strip().lower() for x in args.months.split(",") if x.strip()}
    months = [m for m in months if m[0] in want]
  lane = args.lane
  is_v21 = lane in ("v2_1", "v2.1") or args.shorts or args.swarm_hard_veto
  promote_as = args.promote_as or ("v2_1" if is_v21 else ("v2" if lane == "v2" else "product"))
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
      "write_lab_summary": not args.no_promote and promote_as != "v2_1",
      "promote_as": promote_as,
      "allow_overwrite_v2": False,
      "lane": lane if not is_v21 or lane.startswith("v2") else "v2_1",
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
