#!/usr/bin/env python3
"""Light API stress test (runs inside Docker)."""

from __future__ import annotations

import concurrent.futures
import json
import os
import statistics
import time
import urllib.request
from base64 import b64encode

BASE = os.environ.get("STRESS_BASE", "http://api:8000")
AUTH = b64encode(b"admin:changeme").decode()


def get(path: str) -> tuple[int, float]:
  req = urllib.request.Request(
    f"{BASE}{path}",
    headers={"Authorization": f"Basic {AUTH}"},
  )
  start = time.perf_counter()
  try:
    with urllib.request.urlopen(req, timeout=120) as resp:
      resp.read()
      return resp.status, time.perf_counter() - start
  except Exception:
    return -1, time.perf_counter() - start


def main() -> None:
  ids = json.loads(
    urllib.request.urlopen(
      urllib.request.Request(
        f"{BASE}/signals?limit=50",
        headers={"Authorization": f"Basic {AUTH}"},
      ),
      timeout=60,
    ).read()
  )["items"]
  paths = ["/signals?limit=50"] * 30
  paths += [f"/signals/{s['id']}" for s in ids[:20] for _ in range(2)]
  paths += ["/health"] * 20
  paths += ["/stats/calibration"] * 10
  paths += ["/system"] * 10

  t0 = time.perf_counter()
  with concurrent.futures.ThreadPoolExecutor(20) as ex:
    results = list(ex.map(get, paths))
  total = time.perf_counter() - t0
  lats = sorted(elapsed for _, elapsed in results)
  ok = sum(1 for status, _ in results if status == 200)
  print(
    {
      "requests": len(paths),
      "ok": ok,
      "errors": len(paths) - ok,
      "total_s": round(total, 2),
      "avg_s": round(statistics.mean(lats), 3),
      "p95_s": round(lats[int(len(lats) * 0.95) - 1], 3),
      "max_s": round(max(lats), 3),
    }
  )


if __name__ == "__main__":
  main()
