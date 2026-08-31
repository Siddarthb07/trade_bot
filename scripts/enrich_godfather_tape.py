"""Enrich GodFather tape trades with why-chosen, loss analysis, and OHLC bars.

Safe to re-run. Reads models/godfather_desk_tape.json (or public/tape.json),
writes both models + GodFather-core public/tape.json.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
os.environ.setdefault(
  "POSTGRES_URL",
  "postgresql://smartmoney:changeme@127.0.0.1:5433/smartmoney",
)

from processor.smart_money_gate import rank_pro_buys

CACHE = ROOT / "models" / "intraday_cache"
PAD = 4
TAPE_CANDIDATES = [
  ROOT / "models" / "godfather_desk_tape.json",
  Path(r"C:\Users\siddu\Projects\GodFather-core\apps\dashboard\public\tape.json"),
  ROOT / "models" / "copy_pro_august_use60_tape.json",
]
OUT_MODEL = ROOT / "models" / "godfather_desk_tape.json"
OUT_PUBLIC = Path(r"C:\Users\siddu\Projects\GodFather-core\apps\dashboard\public\tape.json")


def _normalize_tape(data: dict | list) -> dict:
  """Accept desk tape shape or raw session tape list/dict."""
  if isinstance(data, list):
    return {
      "generated_at": __import__("datetime").date.today().isoformat(),
      "claim": "Paper / session simulation. Enriched local tape.",
      "source": "enrich_godfather_tape",
      "trades": data,
      "sessions": [],
    }
  trades = data.get("trades")
  if trades is None and isinstance(data.get("fills"), list):
    trades = data["fills"]
  if trades is None and isinstance(data.get("book"), list):
    trades = data["book"]
  out = dict(data)
  out["trades"] = list(trades or [])
  return out


def load_bars(ticker: str, asof: str) -> list[dict]:
  keys = [
    ticker,
    ticker if str(ticker).endswith(".NS") else f"{ticker}.NS",
    str(ticker).replace(".NS", "") + ".NS",
  ]
  intervals = ("5m", "15m", "1h", "1m")
  for key in keys:
    for interval in intervals:
      path = CACHE / key / f"{asof}_{interval}.json"
      if not path.exists():
        continue
      try:
        raw = json.loads(path.read_text(encoding="utf-8"))
      except Exception:
        continue
      out = []
      for b in raw:
        out.append(
          {
            "ts": b.get("ts") or b.get("date"),
            "open": float(b.get("open") or b.get("close") or 0),
            "high": float(b.get("high") or b.get("close") or 0),
            "low": float(b.get("low") or b.get("close") or 0),
            "close": float(b.get("close") or 0),
            "volume": float(b.get("volume") or 0),
          }
        )
      if out:
        return out
  return []


def slice_bars(bars: list[dict], entry_i: int | None, exit_i: int | None) -> tuple[list[dict], int, int]:
  if not bars:
    return [], 0, 0
  ei = int(entry_i) if entry_i is not None else 0
  xi = int(exit_i) if exit_i is not None else len(bars) - 1
  ei = max(0, min(ei, len(bars) - 1))
  xi = max(ei, min(xi, len(bars) - 1))
  lo = max(0, ei - PAD)
  hi = min(len(bars), xi + PAD + 1)
  window = bars[lo:hi]
  return window, ei - lo, xi - lo


def loss_analysis(t: dict) -> str:
  pnl = float(t.get("pnl") or 0)
  reason = str(t.get("exit_reason") or "")
  pnl_pct = float(t.get("pnl_pct") or 0)
  lev = float(t.get("leverage") or 0)
  fees = float(t.get("fees") or 0)
  if pnl >= 0:
    return f"Closed green via {reason or 'exit'} ({pnl_pct:+.2f}% on notional, lev {lev:.1f}x, fees ₹{fees:.2f})."
  if "stop" in reason:
    return (
      f"Stop hit ({reason}). Price moved against entry; leverage {lev:.1f}x "
      f"amplified notional to {pnl_pct:+.2f}% / ₹{pnl:,.2f} (fees ₹{fees:.2f})."
    )
  if "trail" in reason:
    return f"Trail exit after giveback ({reason}). Final {pnl_pct:+.2f}% / ₹{pnl:,.2f}."
  if "session" in reason or "close" in reason:
    return (
      f"Held to session end red. Path did not recover; fees ₹{fees:.2f}. "
      f"Final {pnl_pct:+.2f}% / ₹{pnl:,.2f}."
    )
  return f"Loss via {reason or 'unknown'}: {pnl_pct:+.2f}% / ₹{pnl:,.2f} (fees ₹{fees:.2f})."


def choice_from_rank(pick: dict | None, alts: list[dict], t: dict) -> str:
  parts = []
  if pick:
    parts.append(
      f"Prior-session bulk BUY ranked by score {pick.get('score')} "
      f"(WR {pick.get('win_rate_eff') or pick.get('win_rate')}, "
      f"deal ₹{float(pick.get('value') or 0):,.0f}, "
      f"entity {pick.get('entity_normalized')}, n={pick.get('n_trades')})."
    )
  else:
    parts.append(
      f"Copy-pro fill {t.get('ticker')} score={t.get('bulk_score')} "
      f"WR={t.get('bulk_wr')} entity={t.get('bulk_entity')}."
    )
  if alts:
    top = ", ".join(f"{a.get('ticker')}({a.get('score')})" for a in alts[:3])
    parts.append(f"Next ranks skipped/not filled: {top}.")
  if t.get("signal_reason"):
    parts.append(f"Signal: {t.get('signal_reason')}.")
  return " ".join(parts)


def enrich_trade(t: dict, picks_cache: dict[str, list[dict]]) -> dict:
  row = dict(t)
  asof = str(row.get("asof") or "")[:10]
  ticker = str(row.get("ticker") or "")
  invested = float(row.get("money_put") or row.get("entry_notional") or 0)
  returned = float(row.get("money_returned") or row.get("exit_notional") or 0)
  fees = float(row.get("fees") or 0)
  pnl = float(row.get("pnl") or 0)
  if returned <= 0 and invested > 0:
    returned = round(invested + pnl + fees, 2)
  row["money_put"] = round(invested, 2)
  row["entry_notional"] = round(invested, 2)
  row["money_returned"] = round(returned, 2)
  row["exit_notional"] = round(returned, 2)
  row["fees"] = round(fees, 4)

  if asof not in picks_cache:
    try:
      rank = rank_pro_buys(
        asof,
        lookback_sessions=1,
        min_win_rate=0.55,
        min_n_trades=1,
        min_deal_value=0.0,
        wr_prior=0.55,
        wr_pseudo_n=0.0,
        limit=8,
      )
      picks_cache[asof] = list(rank.get("picks") or [])
    except Exception as exc:  # noqa: BLE001
      picks_cache[asof] = []
      row["rank_error"] = str(exc)

  picks = picks_cache[asof]
  pick = next((p for p in picks if str(p.get("ticker")) == ticker), None)
  alts = [p for p in picks if str(p.get("ticker")) != ticker]
  if pick:
    row["bulk_entity"] = row.get("bulk_entity") or pick.get("entity_normalized")
    row["bulk_score"] = row.get("bulk_score") if row.get("bulk_score") is not None else pick.get("score")
    row["bulk_wr"] = (
      row.get("bulk_wr")
      if row.get("bulk_wr") is not None
      else pick.get("win_rate_eff") or pick.get("win_rate")
    )
    row["rank"] = next((i + 1 for i, p in enumerate(picks) if str(p.get("ticker")) == ticker), None)
  row["choice_notes"] = choice_from_rank(pick, alts, row)
  row["loss_analysis"] = loss_analysis(row)
  row["alternates"] = [
    {
      "ticker": a.get("ticker"),
      "score": a.get("score"),
      "win_rate": a.get("win_rate_eff") or a.get("win_rate"),
      "entity": a.get("entity_normalized"),
      "value": a.get("value"),
    }
    for a in alts[:5]
  ]

  bars_full = load_bars(ticker, asof)
  window, ei, xi = slice_bars(bars_full, row.get("entry_bar_i"), row.get("exit_bar_i"))
  if not window and bars_full:
    # No bar indices — show full session with estimated entry/exit by price proximity
    window = bars_full
    entry_px = float(row.get("entry_price") or 0)
    exit_px = float(row.get("exit_price") or 0)
    if entry_px:
      ei = min(range(len(window)), key=lambda i: abs(float(window[i]["close"]) - entry_px))
    if exit_px:
      xi = min(range(len(window)), key=lambda i: abs(float(window[i]["close"]) - exit_px))
      if xi < ei:
        xi = ei
  row["bars"] = window
  row["entry_bar_i"] = ei
  row["exit_bar_i"] = xi
  row["pad_before"] = PAD
  row["pad_after"] = PAD
  row["bars_source"] = "intraday_cache" if window else "missing"
  row["entry_ts"] = window[ei]["ts"] if window and 0 <= ei < len(window) else row.get("entry_ts")
  row["exit_ts"] = window[xi]["ts"] if window and 0 <= xi < len(window) else row.get("exit_ts")
  return row


def main() -> None:
  src = next((p for p in TAPE_CANDIDATES if p.exists()), None)
  if not src:
    raise SystemExit("no tape.json found — wait for book export")
  data = _normalize_tape(json.loads(src.read_text(encoding="utf-8")))
  trades = list(data.get("trades") or [])
  print(f"enriching {len(trades)} trades from {src}", flush=True)
  cache: dict[str, list[dict]] = {}
  out_trades = []
  for i, t in enumerate(trades):
    row = enrich_trade(t, cache)
    out_trades.append(row)
    if (i + 1) % 25 == 0 or (i + 1) == len(trades):
      print(f"  {i+1}/{len(trades)} bars_ok={sum(1 for x in out_trades if x.get('bars'))}", flush=True)

  data["trades"] = out_trades
  data["summary"] = {
    **(data.get("summary") or {}),
    "n_trades": len(out_trades),
    "with_bars": sum(1 for t in out_trades if t.get("bars")),
    "with_choice": sum(1 for t in out_trades if t.get("choice_notes")),
    "with_loss_analysis": sum(1 for t in out_trades if t.get("loss_analysis")),
  }
  data["enriched_at"] = __import__("datetime").date.today().isoformat()
  OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
  text = json.dumps(data, indent=2, default=str)
  OUT_MODEL.write_text(text, encoding="utf-8")
  wrote_public = False
  try:
    OUT_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    OUT_PUBLIC.write_text(text, encoding="utf-8")
    wrote_public = True
  except OSError as exc:
    print(f"public write skipped: {exc}", flush=True)
  print(
    f"WROTE model={OUT_MODEL} public={wrote_public} n={len(out_trades)} "
    f"bars={data['summary']['with_bars']} choice={data['summary']['with_choice']} "
    f"analysis={data['summary']['with_loss_analysis']}",
    flush=True,
  )


if __name__ == "__main__":
  main()
