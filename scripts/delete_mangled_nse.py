#!/usr/bin/env python3
"""Delete NSE signals whose Date header was BOM-mangled (bad disclosed_at)."""

from __future__ import annotations

from core.db import SessionLocal
from core.models import ForwardReturn, PortfolioPosition, Signal, SignalScore


def _is_mangled(raw: dict | None) -> bool:
  if not raw:
    return False
  for key in raw:
    key_s = str(key)
    if "date" in key_s.lower() and key_s not in ("Date", "DATE"):
      return True
  return False


def main() -> None:
  db = SessionLocal()
  try:
    ids = [
      s.id
      for s in db.query(Signal.id, Signal.raw_json)
      .filter(Signal.source.in_(["nse_bulk", "nse_block"]), Signal.market == "IN")
      .all()
      if _is_mangled(s.raw_json)
    ]
    print({"mangled_candidates": len(ids)})
    if not ids:
      return
    for i in range(0, len(ids), 500):
      chunk = ids[i : i + 500]
      db.query(ForwardReturn).filter(ForwardReturn.signal_id.in_(chunk)).delete(
        synchronize_session=False
      )
      db.query(SignalScore).filter(SignalScore.signal_id.in_(chunk)).delete(
        synchronize_session=False
      )
      db.query(PortfolioPosition).filter(PortfolioPosition.signal_id.in_(chunk)).update(
        {PortfolioPosition.signal_id: None},
        synchronize_session=False,
      )
      db.query(Signal).filter(Signal.id.in_(chunk)).delete(synchronize_session=False)
      db.commit()
      print({"deleted_through": i + len(chunk)})
    remaining = (
      db.query(Signal)
      .filter(Signal.source.in_(["nse_bulk", "nse_block"]), Signal.market == "IN")
      .count()
    )
    print({"remaining_nse_signals": remaining})
  finally:
    db.close()


if __name__ == "__main__":
  main()
