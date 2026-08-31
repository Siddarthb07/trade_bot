"""F&O / shortable universe helpers — refuse shorts outside the stub list."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "models" / "universes" / "nse_fo_underliers.json"


@lru_cache(maxsize=4)
def load_fo_underliers(path: str | None = None) -> frozenset[str]:
  p = Path(path) if path else DEFAULT_PATH
  data = json.loads(p.read_text(encoding="utf-8"))
  tickers = {str(t).upper().strip() for t in (data.get("tickers") or [])}
  return frozenset(tickers)


def normalize_ns(ticker: str) -> str:
  t = str(ticker or "").upper().strip()
  if not t:
    return t
  if t.endswith(".NS") or t.endswith(".BO"):
    return t
  return f"{t}.NS"


def is_fo_underlier(ticker: str, *, path: str | None = None) -> bool:
  uni = load_fo_underliers(path)
  t = normalize_ns(ticker)
  raw = t.replace(".NS", "").replace(".BO", "")
  return t in uni or raw in uni or f"{raw}.NS" in uni


def allow_short(ticker: str, *, path: str | None = None) -> tuple[bool, str]:
  if is_fo_underlier(ticker, path=path):
    return True, "fo_underlier"
  return False, "short_refused_not_fo_underlier"


def fo_universe_list(*, path: str | None = None) -> list[str]:
  return sorted(load_fo_underliers(path))
