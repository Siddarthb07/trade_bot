"""Host-side NSE historical backfill with localhost Postgres."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

# Force host → published docker port before core.db binds.
os.environ.setdefault(
  "POSTGRES_URL",
  "postgresql://smartmoney:changeme@127.0.0.1:5433/smartmoney",
)
url = os.environ["POSTGRES_URL"]
if "@postgres:" in url:
  os.environ["POSTGRES_URL"] = url.replace("@postgres:5432", "@127.0.0.1:5433")

from ingest.nse import backfill_nse_historical  # noqa: E402
from processor.smart_money_gate import bulk_data_coverage  # noqa: E402


def main() -> None:
  days = int(sys.argv[1]) if len(sys.argv) > 1 else 50
  print(f"backfill_nse_historical days={days}", flush=True)
  try:
    out = backfill_nse_historical(days=days)
    print("backfill", out, flush=True)
  except Exception as exc:  # noqa: BLE001
    print(f"BACKFILL_FAILED {type(exc).__name__}: {exc}", flush=True)
  print("coverage", bulk_data_coverage(since="2026-07-01"), flush=True)


if __name__ == "__main__":
  main()
