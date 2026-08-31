"""Parallel ticker workers — deterministic sort, same ranks as serial."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable


def map_tickers(
  tickers: list[str],
  fn: Callable[[str], dict[str, Any]],
  *,
  max_workers: int = 8,
) -> list[dict[str, Any]]:
  """Run fn per ticker; return results sorted by ticker for determinism."""
  if not tickers:
    return []
  out: dict[str, dict[str, Any]] = {}
  workers = min(max_workers, max(1, len(tickers)))
  with ThreadPoolExecutor(max_workers=workers) as ex:
    futs = {ex.submit(fn, t): t for t in tickers}
    for fut in as_completed(futs):
      t = futs[fut]
      try:
        row = fut.result()
      except Exception as e:  # noqa: BLE001
        row = {"ticker": t, "error": str(e), "eligible": False, "score": 0.0}
      out[t] = row
  return [out[t] for t in sorted(out.keys())]
