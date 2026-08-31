"""Two-sided (long/short) session path math — pure helpers, no I/O.

Long: pnl ~ exit/entry - 1
Short: pnl ~ entry/exit - 1  (equiv. -(exit/entry - 1))
"""

from __future__ import annotations

from typing import Any, Literal, Sequence

Side = Literal["buy", "sell", "long", "short"]


def normalize_side(side: str | None) -> Literal["long", "short"] | None:
  s = (side or "").lower().strip()
  if s in ("buy", "long"):
    return "long"
  if s in ("sell", "short"):
    return "short"
  return None


def signed_return(entry: float, px: float, side: str) -> float:
  """Mark-to-market return from entry for long or short."""
  ns = normalize_side(side)
  if ns is None or entry <= 0:
    return 0.0
  raw = px / entry - 1.0
  return raw if ns == "long" else -raw


def path_exit_two_sided(
  closes: Sequence[float],
  entry_i: int,
  side: str,
  *,
  sl: float,
  tp: float | None = None,
  soft_trail_arm: float | None = None,
  soft_trail: float | None = None,
  protect_only: bool = True,
  exit_at_session_end: bool = True,
) -> dict[str, Any]:
  """Walk closes after entry; return exit index/px/reason/pnl_frac.

  protect_only: hard SL only; winners trail or ride to session close (no hard TP).
  """
  ns = normalize_side(side)
  if ns is None or entry_i < 0 or entry_i >= len(closes):
    return {"ok": False, "reason": "bad_entry"}
  entry = float(closes[entry_i])
  if entry <= 0:
    return {"ok": False, "reason": "bad_entry_px"}

  peak_r = 0.0
  trail_armed = False
  exit_i = entry_i
  exit_px = entry
  exit_reason = "session_horizon"

  for j in range(1, len(closes) - entry_i):
    i = entry_i + j
    px = float(closes[i])
    r = signed_return(entry, px, ns)
    if r <= -abs(sl):
      return {
        "ok": True,
        "side": ns,
        "entry_i": entry_i,
        "entry_px": entry,
        "exit_i": i,
        "exit_px": px,
        "exit_reason": "stop_loss",
        "pnl_frac": r,
      }
    if (not protect_only) and tp is not None and r >= abs(tp):
      return {
        "ok": True,
        "side": ns,
        "entry_i": entry_i,
        "entry_px": entry,
        "exit_i": i,
        "exit_px": px,
        "exit_reason": "take_profit",
        "pnl_frac": r,
      }
    if soft_trail_arm is not None and soft_trail is not None and soft_trail_arm > 0 and soft_trail > 0:
      peak_r = max(peak_r, r)
      if peak_r >= soft_trail_arm:
        trail_armed = True
      if trail_armed and r <= peak_r - soft_trail:
        return {
          "ok": True,
          "side": ns,
          "entry_i": entry_i,
          "entry_px": entry,
          "exit_i": i,
          "exit_px": px,
          "exit_reason": "soft_trail",
          "pnl_frac": r,
        }
    exit_i = i
    exit_px = px
    exit_reason = "session_horizon"

  if exit_at_session_end or protect_only:
    exit_i = len(closes) - 1
    exit_px = float(closes[exit_i])
    exit_reason = "session_close"
  pnl_frac = signed_return(entry, exit_px, ns)
  return {
    "ok": True,
    "side": ns,
    "entry_i": entry_i,
    "entry_px": entry,
    "exit_i": exit_i,
    "exit_px": exit_px,
    "exit_reason": exit_reason,
    "pnl_frac": pnl_frac,
  }


def notional_pnl(entry_notional: float, pnl_frac: float, fees: float) -> float:
  return round(float(entry_notional) * float(pnl_frac) - float(fees), 2)
