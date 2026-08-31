"""Seven-point leak audit on copy_pro 2025 oneshot ledger.

Writes models/copy_pro_2025_leak_audit.json
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
os.environ.setdefault(
  "POSTGRES_URL",
  "postgresql://smartmoney:changeme@127.0.0.1:5433/smartmoney",
)

from sqlalchemy import text

from broker.sizing import confidence_leverage
from processor.smart_money_gate import _eng, prior_session_window, shrunk_win_rate

IST = ZoneInfo("Asia/Kolkata")
ONESHOT = ROOT / "models" / "copy_pro_year_2025_oneshot_10k.json"
OUT = ROOT / "models" / "copy_pro_2025_leak_audit.json"
WIN_DAYS = 90  # 3mo forward window used by investor_stats


def load_trades() -> list[dict]:
  d = json.loads(ONESHOT.read_text(encoding="utf-8"))
  out = []
  for m in d.get("months") or []:
    for t in m.get("trades") or []:
      row = dict(t)
      row["month"] = m["month"]
      row["asof"] = str(row.get("asof") or str(row.get("entry_date") or ""))[:10]
      out.append(row)
  return out


def deal_ist_date(disclosed_at: datetime) -> date:
  return disclosed_at.astimezone(IST).date()


def pit_entity_wr(conn, entity: str, asof: str, *, prior: float = 0.55, pseudo_n: float = 0.0) -> dict:
  """WR from 3mo outcomes matured strictly before asof (deal_ist + 90d < asof)."""
  asof_d = date.fromisoformat(asof[:10])
  mature_before = asof_d  # outcome known only after deal+90d
  rows = conn.execute(
    text(
      """
      SELECT s.disclosed_at, fr.return_pct
      FROM signals s
      JOIN forward_returns fr ON fr.signal_id = s.id AND fr.window = '3mo'
      WHERE s.entity_normalized = :ent
        AND s.market = 'IN'
        AND s.action = ANY(:actions)
        AND fr.return_pct IS NOT NULL
      """
    ),
    {"ent": entity, "actions": ["BUY", "buy", "B"]},
  ).mappings().all()
  usable = []
  for r in rows:
    disc = r["disclosed_at"]
    if disc.tzinfo is None:
      disc = disc.replace(tzinfo=timezone.utc)
    d0 = deal_ist_date(disc)
    mature_on = d0 + timedelta(days=WIN_DAYS)
    if mature_on < asof_d:  # strictly before trade date
      usable.append(float(r["return_pct"]))
  if not usable:
    return {"n": 0, "wr_raw": None, "wr_eff": None, "matured_before_asof": 0}
  wins = sum(1 for x in usable if x > 0)
  wr = wins / len(usable)
  return {
    "n": len(usable),
    "wr_raw": round(wr, 4),
    "wr_eff": round(shrunk_win_rate(wr, len(usable), prior=prior, pseudo_n=pseudo_n), 4),
    "matured_before_asof": len(usable),
  }


def live_entity_wr(conn, entity: str) -> dict:
  row = conn.execute(
    text(
      """
      SELECT win_rate, n_trades FROM investor_stats
      WHERE entity_normalized = :ent AND market = 'IN'
      """
    ),
    {"ent": entity},
  ).mappings().first()
  if not row:
    return {"wr": None, "n": 0}
  return {"wr": float(row["win_rate"]) if row["win_rate"] is not None else None, "n": int(row["n_trades"] or 0)}


def _old_utc_midnight_window(asof: str) -> tuple[datetime, datetime]:
  """Pre-fix window: asof UTC midnight back 1 calendar day (admitted same IST day)."""
  asof_d = date.fromisoformat(asof[:10])
  end = datetime(asof_d.year, asof_d.month, asof_d.day, tzinfo=timezone.utc)
  start = end - timedelta(days=1)
  return start, end


def matching_deals(
  conn,
  ticker: str,
  entity: str,
  asof: str,
  lookback: int = 1,
  *,
  use_old_window: bool = False,
) -> list[dict]:
  if use_old_window:
    start, end = _old_utc_midnight_window(asof)
  else:
    start, end = prior_session_window(asof, lookback)
  bare = ticker.replace(".NS", "")
  rows = conn.execute(
    text(
      """
      SELECT disclosed_at, ticker, entity_normalized, value, action, source
      FROM signals
      WHERE market = 'IN'
        AND source = ANY(:sources)
        AND action = ANY(:actions)
        AND disclosed_at >= :start AND disclosed_at < :end
        AND (
          ticker = :bare OR ticker = :ns OR ticker_normalized = :ns
          OR ticker_normalized = :bare
        )
        AND (:ent = '' OR entity_normalized = :ent)
      ORDER BY disclosed_at DESC
      """
    ),
    {
      "sources": ["nse_bulk", "nse_block", "bse_bulk"],
      "actions": ["BUY", "buy", "B"],
      "start": start,
      "end": end,
      "bare": bare,
      "ns": f"{bare}.NS" if not bare.endswith(".NS") else bare,
      "ent": entity or "",
    },
  ).mappings().all()
  return [dict(r) for r in rows]


def audit_same_day(trades: list[dict], conn) -> dict:
  """Flag ledger trades that the *old* UTC window admitted but honest IST prior would not."""
  flags = []
  monday = []
  same_ist = []
  for t in trades:
    asof = t["asof"]
    entity = str(t.get("bulk_entity") or "")
    ticker = str(t.get("ticker") or "")
    # Pull deals under the OLD window (what the contaminated book used)
    deals = matching_deals(conn, ticker, entity, asof, use_old_window=True)
    old_start, old_end = _old_utc_midnight_window(asof)
    honest_start, honest_end = prior_session_window(asof, 1)
    asof_d = date.fromisoformat(asof)
    for d in deals:
      disc = d["disclosed_at"]
      if disc.tzinfo is None:
        disc = disc.replace(tzinfo=timezone.utc)
      ist_d = deal_ist_date(disc)
      in_old = old_start <= disc < old_end
      in_honest = honest_start <= disc < honest_end
      same_ist_day = ist_d == asof_d
      if in_old and not in_honest:
        row = {
          "asof": asof,
          "ticker": ticker,
          "entity": entity,
          "disclosed_at_utc": disc.isoformat(),
          "deal_ist_date": ist_d.isoformat(),
          "same_ist_day": same_ist_day,
          "weekday": asof_d.strftime("%A"),
          "pnl": t.get("pnl"),
        }
        flags.append(row)
        if asof_d.weekday() == 0:
          monday.append(row)
        if same_ist_day:
          same_ist.append(row)
        break
  return {
    "n_flagged": len(flags),
    "n_monday_flagged": len(monday),
    "n_same_ist_day": len(same_ist),
    "pnl_flagged": round(sum(float(x.get("pnl") or 0) for x in flags), 2),
    "examples": flags[:20],
    "monday_examples": monday[:10],
    "same_ist_examples": same_ist[:10],
    "note": "Compares old UTC-midnight window vs fixed IST prior-session window on contaminated ledger",
  }


def audit_wr_leak(trades: list[dict], conn) -> dict:
  leaked = []
  thin = []
  entity_first_last = {}
  for t in trades:
    entity = str(t.get("bulk_entity") or "")
    asof = t["asof"]
    if not entity:
      continue
    live = live_entity_wr(conn, entity)
    pit0 = pit_entity_wr(conn, entity, asof, prior=0.55, pseudo_n=0.0)
    pit5 = pit_entity_wr(conn, entity, asof, prior=0.55, pseudo_n=5.0)
    used = float(t.get("confidence") or 0)
    # mismatch: live/used WR not explainable by PIT matured sample
    leak = False
    reason = []
    if pit0["n"] == 0 and used >= 0.55:
      leak = True
      reason.append("no_pit_matured_outcomes_but_scored")
    if live["wr"] is not None and pit0["wr_raw"] is not None and abs(live["wr"] - pit0["wr_raw"]) > 0.05:
      leak = True
      reason.append("live_wr_differs_from_pit")
    if pit0["n"] > 0 and pit0["n"] <= 3 and used >= 0.90:
      thin.append(
        {
          "asof": asof,
          "ticker": t.get("ticker"),
          "entity": entity,
          "pit_n": pit0["n"],
          "pit_wr": pit0["wr_raw"],
          "used_conf": used,
          "pnl": t.get("pnl"),
        }
      )
    if leak:
      leaked.append(
        {
          "asof": asof,
          "ticker": t.get("ticker"),
          "entity": entity,
          "used_conf": used,
          "live_wr": live["wr"],
          "live_n": live["n"],
          "pit_n": pit0["n"],
          "pit_wr_raw": pit0["wr_raw"],
          "pit_wr_eff_pseudo5": pit5["wr_eff"],
          "reasons": reason,
          "pnl": t.get("pnl"),
          "leverage": t.get("leverage"),
          "entry_notional": t.get("entry_notional"),
        }
      )
    fl = entity_first_last.setdefault(entity, {"first": asof, "last": asof, "n": 0, "pnl": 0.0})
    fl["first"] = min(fl["first"], asof)
    fl["last"] = max(fl["last"], asof)
    fl["n"] += 1
    fl["pnl"] += float(t.get("pnl") or 0)

  # PRASOON-shaped: rare early, heavy late
  late_bloomers = []
  for ent, fl in entity_first_last.items():
    if fl["n"] < 3:
      continue
    # heuristic: first appearance in H2 and many trades
    if fl["first"] >= "2025-07-01" and fl["n"] >= 3:
      late_bloomers.append({"entity": ent, **fl, "pnl": round(fl["pnl"], 2)})

  return {
    "n_leaked_trades": len(leaked),
    "pnl_leaked": round(sum(float(x["pnl"] or 0) for x in leaked), 2),
    "n_thin_high_conf": len(thin),
    "leaked_examples": sorted(leaked, key=lambda x: -abs(float(x.get("pnl") or 0)))[:25],
    "thin_high_conf_examples": thin[:15],
    "late_bloom_entities": sorted(late_bloomers, key=lambda x: -x["n"])[:15],
  }


def audit_corp_actions(trades: list[dict]) -> dict:
  try:
    import yfinance as yf
  except ImportError:
    return {"error": "yfinance missing"}
  tickers = sorted({str(t.get("ticker")) for t in trades if t.get("ticker")})
  hits = []
  for tk in tickers:
    try:
      t = yf.Ticker(tk)
      splits = t.splits
      divs = t.dividends
    except Exception:
      continue
    # holding year 2025
    def in_2025(idx):
      try:
        return str(idx.date())[:4] == "2025"
      except Exception:
        return False

    s2025 = []
    if splits is not None and len(splits):
      s2025 = [(str(i.date()), float(v)) for i, v in splits.items() if in_2025(i)]
    d2025 = []
    if divs is not None and len(divs):
      d2025 = [(str(i.date()), float(v)) for i, v in divs.items() if in_2025(i)]
    if s2025 or d2025:
      # trades overlapping
      related = [
        {
          "asof": tr["asof"],
          "pnl": tr.get("pnl"),
          "entry": tr.get("entry_price"),
          "exit": tr.get("exit_price"),
        }
        for tr in trades
        if tr.get("ticker") == tk
      ]
      hits.append({"ticker": tk, "splits_2025": s2025, "dividends_2025": d2025, "trades": related})
  return {"n_tickers_checked": len(tickers), "n_with_corp_action_2025": len(hits), "hits": hits}


def audit_sizing(trades: list[dict]) -> dict:
  max_lev = []
  second_slotish = defaultdict(list)
  for t in trades:
    conf = float(t.get("confidence") or 0)
    lev = float(t.get("leverage") or 0)
    intended = confidence_leverage(conf, max_leverage=5.0)
    asof = t["asof"]
    second_slotish[asof].append(t)
    if conf >= 0.90 or lev >= 4.5:
      max_lev.append(
        {
          "asof": asof,
          "ticker": t.get("ticker"),
          "entity": t.get("bulk_entity"),
          "conf": conf,
          "leverage": lev,
          "intended_lev": intended,
          "pnl": t.get("pnl"),
          "notional": t.get("entry_notional"),
          "got_cap_bet": lev >= 4.5 or intended >= 4.5,
        }
      )
  multi = {k: v for k, v in second_slotish.items() if len(v) >= 2}
  second_flags = []
  for asof, xs in multi.items():
    xs = sorted(xs, key=lambda t: -float(t.get("bulk_score") or t.get("confidence") or 0))
    if len(xs) < 2:
      continue
    a, b = xs[0], xs[1]
    second_flags.append(
      {
        "asof": asof,
        "first": a.get("ticker"),
        "second": b.get("ticker"),
        "first_conf": a.get("confidence"),
        "second_conf": b.get("confidence"),
        "second_pnl": b.get("pnl"),
        "note": "2nd slot also sized from same conf/WR surface",
      }
    )
  return {
    "n_high_conf_or_near_cap": len(max_lev),
    "pnl_high_conf": round(sum(float(x["pnl"] or 0) for x in max_lev), 2),
    "examples": sorted(max_lev, key=lambda x: -abs(float(x.get("pnl") or 0)))[:20],
    "n_multi_fill_days": len(multi),
    "second_slot_examples": second_flags[:15],
  }


def audit_entity_tail(trades: list[dict]) -> dict:
  by_e = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
  for t in trades:
    e = str(t.get("bulk_entity") or "?")
    pnl = float(t.get("pnl") or 0)
    by_e[e]["n"] += 1
    by_e[e]["pnl"] += pnl
    if pnl > 0:
      by_e[e]["wins"] += 1
  ranked = sorted(by_e.items(), key=lambda x: -x[1]["pnl"])
  total = sum(float(t.get("pnl") or 0) for t in trades)
  top5 = ranked[:5]
  win_tail = sorted(trades, key=lambda t: -float(t.get("pnl") or 0))[:20]
  tail_ents = Counter(str(t.get("bulk_entity") or "?") for t in win_tail)
  return {
    "total_pnl": round(total, 2),
    "top5_entities_by_pnl": [
      {"entity": e, "n": v["n"], "pnl": round(v["pnl"], 2), "share_pct": round(100 * v["pnl"] / total, 1) if total else None}
      for e, v in top5
    ],
    "top5_share_pct": round(100 * sum(v["pnl"] for _, v in top5) / total, 1) if total else None,
    "winning_tail_20_entity_counts": tail_ents.most_common(10),
  }


def audit_regime(trades: list[dict]) -> dict:
  buckets = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
  for t in trades:
    reason = str(t.get("signal_reason") or "")
    reg = "unknown"
    if "regime=" in reason:
      reg = reason.split("regime=")[-1].split("|")[0].strip() or "unknown"
    pnl = float(t.get("pnl") or 0)
    buckets[reg]["n"] += 1
    buckets[reg]["pnl"] += pnl
    if pnl > 0:
      buckets[reg]["wins"] += 1
  out = {}
  for k, v in buckets.items():
    out[k] = {
      "n": v["n"],
      "pnl": round(v["pnl"], 2),
      "wr": round(v["wins"] / v["n"], 3) if v["n"] else None,
      "avg_pnl": round(v["pnl"] / v["n"], 2) if v["n"] else None,
    }
  return out


def audit_fees(trades: list[dict]) -> dict:
  bad = []
  for t in trades:
    put = float(t.get("entry_notional") or 0)
    ret = float(t.get("exit_notional") or 0)
    fees = float(t.get("fees") or 0)
    pnl = float(t.get("pnl") or 0)
    expect = round(ret - put - fees, 2)
    if abs(expect - pnl) > 0.05:
      bad.append({"asof": t["asof"], "ticker": t.get("ticker"), "pnl": pnl, "expect": expect, "fees": fees})
  return {
    "n_checked": len(trades),
    "n_identity_breaks": len(bad),
    "sum_fees": round(sum(float(t.get("fees") or 0) for t in trades), 2),
    "sum_pnl": round(sum(float(t.get("pnl") or 0) for t in trades), 2),
    "examples": bad[:10],
    "note": "Identity pnl = exit_notional - entry_notional - fees (single CostModel+broker fee sum)",
  }


def main() -> None:
  trades = load_trades()
  print(f"auditing {len(trades)} trades", flush=True)
  report: dict = {
    "generated_at": date.today().isoformat(),
    "n_trades": len(trades),
    "claim": "Leak audit on rebuilt 2025 ledger; reconstructs PIT WR vs live investor_stats",
  }
  with _eng().connect() as conn:
    print("1) WR leak / thin sample…", flush=True)
    report["1_wr_leak"] = audit_wr_leak(trades, conn)
    print(
      f"   leaked={report['1_wr_leak']['n_leaked_trades']} pnl={report['1_wr_leak']['pnl_leaked']}",
      flush=True,
    )
    print("2) Same-day IST/UTC…", flush=True)
    report["2_same_day_window"] = audit_same_day(trades, conn)
    print(
      f"   flagged={report['2_same_day_window']['n_flagged']} monday={report['2_same_day_window']['n_monday_flagged']}",
      flush=True,
    )

  print("3) Corporate actions…", flush=True)
  report["3_corp_actions"] = audit_corp_actions(trades)
  print(f"   hits={report['3_corp_actions'].get('n_with_corp_action_2025')}", flush=True)

  print("4) Sizing / 2nd slot…", flush=True)
  report["4_sizing"] = audit_sizing(trades)

  print("5) Entity tail…", flush=True)
  report["5_entity_tail"] = audit_entity_tail(trades)

  print("6) Regime…", flush=True)
  report["6_regime"] = audit_regime(trades)

  print("7) Fees…", flush=True)
  report["7_fees"] = audit_fees(trades)

  OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
  print(f"WROTE {OUT}", flush=True)


if __name__ == "__main__":
  main()
