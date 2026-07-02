"""Rescore all signals to populate Phase 1 timeframe fields."""

from __future__ import annotations

from core.db import SessionLocal
from core.models import Signal
from processor.scoring import score_signal


def main() -> None:
  db = SessionLocal()
  try:
    signals = db.query(Signal).all()
    n = 0
    for signal in signals:
      score_signal(db, signal)
      n += 1
      if n % 50 == 0:
        print(f"rescored {n}/{len(signals)}")
    print(f"Done — rescored {n} signals with timeframe fields")
  finally:
    db.close()


if __name__ == "__main__":
  main()
