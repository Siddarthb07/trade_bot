#!/usr/bin/env python3
"""Backfill NSE archive data."""

import sys

from ingest.nse import backfill_nse_archive


def main() -> None:
  limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
  result = backfill_nse_archive(limit=limit)
  print(result)


if __name__ == "__main__":
  main()
