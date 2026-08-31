"""Intraday OHLCV via yfinance — session bars for ORB / day-sim (not daily misuse)."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 300
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_DISK_CACHE_DIR = Path(__file__).resolve().parents[2] / "models" / "intraday_cache"
_INTERVAL_OR_BARS: dict[str, int] = {"1m": 15, "5m": 5, "15m": 2, "30m": 1, "1h": 1, "60m": 1}

# NSE cash approx; US RTH — used to filter same-session bars
_IN_SESSION = (9 * 60 + 15, 15 * 60 + 30)  # minutes from midnight IST-ish (yfinance often IST-naive for .NS)
_US_SESSION = (9 * 60 + 30, 16 * 60)  # ET wall-clock as returned by yfinance


def _cache_get(key: str) -> list[dict[str, Any]] | None:
  hit = _cache.get(key)
  if not hit:
    return None
  ts, data = hit
  if time.monotonic() - ts > _CACHE_TTL_SEC:
    _cache.pop(key, None)
    return None
  return data


def _cache_set(key: str, data: list[dict[str, Any]]) -> None:
  _cache[key] = (time.monotonic(), data)


def default_open_range_bars(interval: str) -> int:
  return _INTERVAL_OR_BARS.get(interval.lower(), 5)


def _disk_cache_path(ticker: str, day: str, interval: str) -> Path:
  safe = ticker.replace("/", "_")
  return _DISK_CACHE_DIR / safe / f"{day}_{interval}.json"


def _disk_cache_get(ticker: str, day: str, interval: str) -> list[dict[str, Any]] | None:
  path = _disk_cache_path(ticker, day, interval)
  if not path.exists():
    return None
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return None


def _disk_cache_set(ticker: str, day: str, interval: str, data: list[dict[str, Any]]) -> None:
  path = _disk_cache_path(ticker, day, interval)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(data), encoding="utf-8")


def load_disk_session_bars(
  ticker: str,
  session_date: str,
  *,
  interval: str = "5m",
) -> list[dict[str, Any]]:
  """Disk-cache only — never hits the network. Empty if miss."""
  day = str(session_date)[:10]
  for iv in (interval, "1h", "5m", "15m"):
    hit = _disk_cache_get(ticker, day, iv)
    if hit:
      return hit
  return []


def probe_intraday_floor(ticker: str = "RELIANCE.NS", interval: str = "5m") -> date | None:
  """Earliest session date with intraday bars for interval (best-effort)."""
  period = "730d" if interval in ("1h", "60m") else "60d"
  try:
    hist = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if hist is None or hist.empty:
      return None
    first = hist.index.min()
    return first.date() if hasattr(first, "date") else pd.Timestamp(first).date()
  except Exception:
    return None


def pick_interval_for_date(session_day: str, preferred: str = "5m") -> str:
  """Prefer finer bars when Yahoo still has them; else fall back."""
  if preferred == "1h":
    return "1h"
  try:
    d = datetime.fromisoformat(session_day[:10]).date()
  except Exception:
    return preferred if preferred != "auto" else "5m"
  today = datetime.now(timezone.utc).date()
  floor_1m = today - timedelta(days=6)
  floor_5m = today - timedelta(days=55)
  if preferred == "1m":
    return "1m" if d >= floor_1m else ("5m" if d >= floor_5m else "1h")
  if preferred in ("5m", "15m", "30m", "auto") and d >= floor_5m:
    return "5m" if preferred == "auto" else preferred
  return "1h"


def _minutes_of_day(ts) -> int | None:
  try:
    if hasattr(ts, "hour"):
      return int(ts.hour) * 60 + int(ts.minute)
  except Exception:
    return None
  return None


def _in_session(ts, market: str) -> bool:
  m = _minutes_of_day(ts)
  if m is None:
    return True
  lo, hi = _IN_SESSION if market.upper() == "IN" else _US_SESSION
  return lo <= m <= hi


def fetch_intraday_bars(
  ticker: str,
  *,
  session_date: str | date | None = None,
  interval: str = "5m",
  market: str | None = None,
  lookback_days: int = 5,
) -> list[dict[str, Any]]:
  """Return list of {ts, open, high, low, close, volume} for one session or recent days.

  yfinance intraday history is limited (~60d for 5m). Empty list on failure.
  """
  mkt = (market or ("IN" if ".NS" in ticker or ".BO" in ticker else "US")).upper()
  if isinstance(session_date, date) and not isinstance(session_date, datetime):
    day = session_date.isoformat()
  elif session_date:
    day = str(session_date)[:10]
  else:
    day = datetime.now(timezone.utc).date().isoformat()

  # adj0 = auto_adjust=False; busts older cache written under auto_adjust=True
  cache_key = f"{ticker}:{interval}:{day}:{mkt}:{lookback_days}:adj0"
  cached = _cache_get(cache_key)
  if cached is not None:
    return cached
  disk = _disk_cache_get(ticker, day, interval)
  if disk is not None:
    _cache_set(cache_key, disk)
    return disk

  end = datetime.fromisoformat(day).date() + timedelta(days=1)
  start = end - timedelta(days=max(lookback_days, 2))
  out: list[dict[str, Any]] = []
  hist = None
  fetchers = (
    lambda: yf.Ticker(ticker).history(
      start=start.isoformat(),
      end=end.isoformat(),
      interval=interval,
      auto_adjust=False,
    ),
    lambda: yf.download(
      ticker,
      start=start.isoformat(),
      end=end.isoformat(),
      interval=interval,
      auto_adjust=False,
      progress=False,
      threads=False,
    ),
    lambda: yf.Ticker(ticker).history(period=f"{max(lookback_days, 5)}d", interval=interval, auto_adjust=False),
  )
  for attempt, fetch in enumerate(fetchers):
    if attempt:
      time.sleep(min(2.0 ** attempt, 4.0))
    try:
      hist = fetch()
      if hist is not None and not getattr(hist, "empty", True):
        break
      hist = None
    except Exception as exc:
      logger.warning("intraday fetch attempt %s for %s: %s", attempt + 1, ticker, exc)
      hist = None
  try:
    if hist is None or getattr(hist, "empty", True):
      # Fallback: 1h bars for sessions outside 5m rolling window
      if interval != "1h" and mkt == "IN":
        alt = fetch_intraday_bars(
          ticker, session_date=day, interval="1h", market=market, lookback_days=lookback_days
        )
        if alt:
          _cache_set(cache_key, alt)
          return alt
      return []
    # Flatten MultiIndex columns if present (yf sometimes returns (OHLC, ticker))
    if isinstance(hist.columns, pd.MultiIndex):
      # yfinance download: (Field, Ticker) — keep OHLCV field names only
      try:
        hist.columns = hist.columns.get_level_values(0)
      except Exception:
        hist.columns = [c[0] if isinstance(c, tuple) else c for c in hist.columns]
    hist = hist.sort_index()
    for idx, row in hist.iterrows():
      try:
        d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        if d != day:
          continue
        if not _in_session(idx, mkt):
          continue
        close_raw = row.get("Close") if hasattr(row, "get") else None
        if close_raw is None and "Close" in getattr(row, "index", []):
          close_raw = row["Close"]
        if close_raw is None:
          for cname in ("Close", "close"):
            if cname in hist.columns:
              close_raw = row[cname] if cname in row.index else None
              if close_raw is not None:
                break
        if close_raw is None or (isinstance(close_raw, float) and close_raw != close_raw):
          continue
        close = float(close_raw)

        def _ox(name: str) -> float:
          if name not in row.index:
            return close
          v = row[name]
          if v is None or (isinstance(v, float) and v != v):
            return close
          return float(v)

        vol_raw = row["Volume"] if "Volume" in row.index else 0
        try:
          vol = int(vol_raw) if vol_raw == vol_raw else 0
        except Exception:
          vol = 0
        out.append(
          {
            "ts": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
            "date": d,
            "open": _ox("Open"),
            "high": _ox("High"),
            "low": _ox("Low"),
            "close": close,
            "volume": vol,
          }
        )
      except Exception:
        continue
  except Exception as exc:
    logger.warning("intraday fetch failed for %s: %s", ticker, exc)
    return []

  _cache_set(cache_key, out)
  if out:
    _disk_cache_set(ticker, day, interval, out)
  return out


def session_closes(bars: list[dict[str, Any]]) -> list[float]:
  return [float(b["close"]) for b in bars if b.get("close") is not None]


def open_range_from_session(
  bars: list[dict[str, Any]],
  *,
  open_range_bars: int = 5,
) -> tuple[list[float], float | None]:
  """Return (session close series, last close) or ([], None)."""
  closes = session_closes(bars)
  if len(closes) < open_range_bars + 2:
    return closes, None
  return closes, closes[-1]
