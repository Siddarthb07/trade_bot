#!/usr/bin/env python3

"""Backfill NSE archive + historical data."""



import sys



from ingest.nse import backfill_nse_archive, backfill_nse_historical





def main() -> None:

  if len(sys.argv) > 1 and sys.argv[1] == "historical":

    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90

    result = backfill_nse_historical(days=days)

  else:

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2000

    result = backfill_nse_archive(limit=limit)

  print(result)





if __name__ == "__main__":

  main()

