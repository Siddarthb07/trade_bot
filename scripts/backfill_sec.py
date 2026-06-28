#!/usr/bin/env python3
"""Backfill SEC Form 4 filings."""

import sys

from ingest.sec import backfill_sec


def main() -> None:
  limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
  result = backfill_sec(limit=limit)
  print(result)


if __name__ == "__main__":
  main()
