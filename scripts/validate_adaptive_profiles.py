"""Validate / freeze adaptive profiles — Stage B gate (n>=30, hit>=85%, expectancy>0)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.profile_validate import MIN_OOS, validate_profiles  # noqa: E402

PROFILE = ROOT / "models" / "ticker_adaptive_profiles.json"


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--require-eligible", action="store_true", help="Fail if no eligible tickers")
  ap.add_argument("--path", type=Path, default=PROFILE)
  args = ap.parse_args()
  if not args.path.exists():
    print(f"FAIL: {args.path} missing", file=sys.stderr)
    return 2
  data = json.loads(args.path.read_text(encoding="utf-8"))
  errs = validate_profiles(data, require_eligible=args.require_eligible)
  if errs:
    print("FAIL adaptive profile validation:")
    for e in errs:
      print(f"  - {e}")
    return 1
  print(
    f"OK: {len(data.get('eligible_tickers') or [])} eligible · "
    f"min_oos={data.get('min_oos_trades', MIN_OOS)} · generated={data.get('generated_at')}"
  )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
