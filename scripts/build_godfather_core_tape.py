"""Build GodFather-core public/tape.json from copy-pro artifacts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"C:\Users\siddu\projects\trade_bot")
OUT = Path(r"C:\Users\siddu\Projects\GodFather-core\apps\dashboard\public\tape.json")

trades: list[dict] = []

aug = json.loads((ROOT / "models" / "copy_pro_august_use60_tape.json").read_text(encoding="utf-8"))
for t in aug.get("trades") or []:
  trades.append(
    {
      "asof": t.get("asof"),
      "ticker": t.get("ticker"),
      "side": "long",
      "entry_price": t.get("entry_px") or t.get("entry_price"),
      "exit_price": t.get("exit_px") or t.get("exit_price"),
      "entry_notional": t.get("entry_notional"),
      "exit_notional": t.get("exit_notional"),
      "money_put": t.get("entry_notional"),
      "money_returned": t.get("exit_notional"),
      "qty": t.get("qty"),
      "leverage": t.get("lev") or t.get("leverage"),
      "pnl": t.get("pnl"),
      "pnl_pct": t.get("pnl_pct"),
      "exit_reason": t.get("exit") or t.get("exit_reason"),
      "slot_capital": t.get("slot_capital"),
      "signal_reason": "copy_bulk_pro",
      "choice_notes": "August use60 copy_bulk_pro session fill",
    }
  )

week = json.loads((ROOT / "models" / "copy_pro_last_week_trace.json").read_text(encoding="utf-8"))
for day in week.get("daily") or []:
  for t in day.get("trades") or []:
    bm = t.get("bulk_meta") or {}
    cause = t.get("cause") or {}
    trades.append(
      {
        "asof": day.get("asof"),
        "ticker": t.get("ticker"),
        "side": "long",
        "entry_price": t.get("entry_price"),
        "exit_price": t.get("exit_price"),
        "entry_notional": t.get("entry_notional"),
        "exit_notional": t.get("exit_notional"),
        "money_put": t.get("entry_notional") or t.get("money_put"),
        "money_returned": t.get("exit_notional") or t.get("money_returned"),
        "qty": t.get("qty"),
        "leverage": t.get("leverage"),
        "pnl": t.get("pnl"),
        "pnl_pct": t.get("pnl_pct"),
        "fees": t.get("fees"),
        "exit_reason": t.get("exit_reason"),
        "slot_capital": t.get("slot_capital"),
        "signal_reason": t.get("signal_reason"),
        "bulk_entity": bm.get("entity_normalized"),
        "bulk_score": bm.get("score"),
        "bulk_wr": bm.get("win_rate"),
        "choice_notes": (
          f"Ranked pick score={bm.get('score')} WR={bm.get('win_rate')} "
          f"entity={bm.get('entity_normalized')} deal={bm.get('value')}"
        ),
        "loss_analysis": cause.get("primary") or "",
        "alternates": (day.get("top_bulk_picks") or [])[1:5],
      }
    )

seen: set[tuple] = set()
uniq: list[dict] = []
for t in trades:
  key = (t.get("asof"), t.get("ticker"), t.get("entry_price"), t.get("pnl"))
  if key in seen:
    continue
  seen.add(key)
  uniq.append(t)

invested = sum(float(t.get("entry_notional") or t.get("money_put") or 0) for t in uniq)
payload = {
  "generated_at": "2026-08-30",
  "claim": "paper/session-sim only; modeled India costs ~30 bps RT; not live fills",
  "source": "copy_pro_august_use60_tape + copy_pro_last_week_trace",
  "summary": {
    "n_trades": len(uniq),
    "wins": sum(1 for t in uniq if float(t.get("pnl") or 0) > 0),
    "losses": sum(1 for t in uniq if float(t.get("pnl") or 0) <= 0),
    "invested_total": round(invested, 2),
    "capital_start": aug.get("capital_start"),
    "capital_end": aug.get("capital_end"),
  },
  "trades": uniq,
  "sessions": [],
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"wrote {OUT} n={len(uniq)} invested={invested:.2f}")
