"""Oracle long+short session-close ceiling on synthetic F&O path — no network.

Honesty: proves plumbing of two-sided ceiling math. Real ceiling needs cached bars.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.two_sided import path_exit_two_sided, signed_return

OUT = ROOT / "models" / "oracle_two_sided_ceiling_synthetic.json"


def main() -> None:
  # Synthetic: best long day + best short day on same path
  up = [100 + i * 0.5 for i in range(20)]
  down = [100 - i * 0.5 for i in range(20)]
  long_ex = path_exit_two_sided(up, 5, "buy", sl=0.99, protect_only=True)
  short_ex = path_exit_two_sided(down, 5, "sell", sl=0.99, protect_only=True)
  # Oracle pick per day
  days = []
  for label, closes, side in (("up", up, "buy"), ("down", down, "sell")):
    best = signed_return(closes[5], closes[-1], side)
    days.append({"day": label, "side": side, "session_close_ret_pct": round(100 * best, 3)})
  report = {
    "generated_at": date.today().isoformat(),
    "mode": "synthetic",
    "claim": "Synthetic oracle only — replace with F&O disk-cache ceiling before live ambition",
    "long_path": long_ex,
    "short_path": short_ex,
    "days": days,
    "mean_oracle_pct": round(sum(d["session_close_ret_pct"] for d in days) / len(days), 3),
  }
  OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
