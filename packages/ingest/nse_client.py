"""Direct NSE HTTP client for bulk and block deals."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
NSE_HOME = "https://www.nseindia.com"
LARGE_DEALS_URL = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
ARCHIVE_BULK_URL = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
ARCHIVE_BLOCK_URL = "https://nsearchives.nseindia.com/content/equities/block.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/block-deal",
}


class NSEClient:
  def __init__(self, min_interval: float = 3.0) -> None:
    self.session = requests.Session()
    self.session.headers.update(HEADERS)
    self.min_interval = min_interval
    self._last_request = 0.0

  def _throttle(self) -> None:
    elapsed = time.time() - self._last_request
    if elapsed < self.min_interval:
      time.sleep(self.min_interval - elapsed)
    self._last_request = time.time()

  def _warmup(self) -> None:
    self._throttle()
    self.session.get(NSE_HOME, timeout=30)

  def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
    for attempt in range(3):
      self._throttle()
      try:
        response = self.session.get(url, params=params, timeout=30)
        if response.status_code == 403:
          self._warmup()
          time.sleep(2 ** attempt)
          continue
        response.raise_for_status()
        return response.json()
      except requests.RequestException as exc:
        logger.warning("NSE request failed attempt %s: %s", attempt + 1, exc)
        self._warmup()
        time.sleep(2 ** attempt)
    raise RuntimeError(f"NSE request failed after retries: {url}")

  def fetch_live_deals(self, mode: str) -> list[dict[str, Any]]:
    self._warmup()
    data = self._get_json(LARGE_DEALS_URL, params={"mode": mode})
    rows = data if isinstance(data, list) else data.get("data", data.get("bulk", []))
    if not rows:
      return []
    return [self._normalize_live_row(row, mode) for row in rows]

  def fetch_archive_csv(self, mode: str) -> list[dict[str, Any]]:
    url = ARCHIVE_BULK_URL if mode == "bulk_deals" else ARCHIVE_BLOCK_URL
    self._warmup()
    self._throttle()
    response = self.session.get(url, timeout=60)
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.text))
    return [self._normalize_archive_row(row, mode) for _, row in df.iterrows() if _valid_archive_row(row)]

  def fetch_fii_dii(self) -> list[dict[str, Any]]:
    self._warmup()
    data = self._get_json(f"{NSE_HOME}/api/fiidiiTradeReact")
    return data if isinstance(data, list) else data.get("data", [])

  def fetch_corp_announcements(
    self,
    from_date: datetime,
    to_date: datetime,
  ) -> list[dict[str, Any]]:
    self._warmup()
    params = {
      "index": "equities",
      "from_date": from_date.strftime("%d-%m-%Y"),
      "to_date": to_date.strftime("%d-%m-%Y"),
    }
    data = self._get_json(f"{NSE_HOME}/api/corporate-announcements", params=params)
    if isinstance(data, list):
      return data
    return data.get("data", []) if isinstance(data, dict) else []

  def fetch_bhavcopy_csv(self, trade_date: datetime) -> str | None:
    """Full equity bhavcopy for a trading day (DDMMYYYY)."""
    self._warmup()
    fname = trade_date.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{fname}.csv"
    self._throttle()
    response = self.session.get(url, timeout=90)
    if response.status_code != 200 or "SYMBOL" not in response.text[:200].upper():
      return None
    return response.text

  def fetch_historical_deals(
    self,
    mode: str,
    from_date: datetime,
    to_date: datetime,
  ) -> list[dict[str, Any]]:
    """NSE historical bulk/block deals for a date range."""
    endpoint = "bulk-deals" if mode == "bulk_deals" else "block-deals"
    url = f"{NSE_HOME}/api/historical/{endpoint}"
    params = {
      "from": from_date.strftime("%d-%m-%Y"),
      "to": to_date.strftime("%d-%m-%Y"),
    }
    self._warmup()
    data = self._get_json(url, params=params)
    rows = data if isinstance(data, list) else data.get("data", [])
    out: list[dict[str, Any]] = []
    for row in rows:
      try:
        out.append(self._normalize_live_row(row, mode))
      except Exception as exc:
        logger.debug("Skip historical row: %s", exc)
    return out

  def _normalize_live_row(self, row: dict[str, Any], mode: str) -> dict[str, Any]:
    symbol = str(row.get("symbol") or row.get("SYMBOL") or "").strip()
    client = str(row.get("clientName") or row.get("CLIENT_NAME") or row.get("buyerName") or "UNKNOWN")
    action = str(row.get("buySell") or row.get("BUY_SELL") or row.get("transactionType") or "BUY")
    qty = _to_float(row.get("quantity") or row.get("QUANTITY"))
    price = _to_float(row.get("tradePrice") or row.get("TRADE_PRICE") or row.get("avgPrice"))
    value = _to_float(row.get("value") or row.get("VALUE"))
    if value is None and qty and price:
      value = qty * price
    disclosed = _parse_date(
      row.get("date")
      or row.get("DATE")
      or row.get("Date")
      or row.get("dealDate")
      or datetime.now(IST).date()
    )
    source = "nse_bulk" if "bulk" in mode else "nse_block"
    source_ref = _make_ref(source, symbol, client, action, disclosed, qty, price)
    return {
      "source": source,
      "source_ref": source_ref,
      "market": "IN",
      "entity": client,
      "ticker": symbol,
      "action": action,
      "qty": qty,
      "value": value,
      "disclosed_at": disclosed,
      "source_url": "https://www.nseindia.com/market-data/block-deal",
      "raw_json": row,
    }

  def _normalize_archive_row(self, row: pd.Series, mode: str) -> dict[str, Any]:
    symbol = str(row.get("SYMBOL") or row.get("Symbol") or "").strip()
    client = str(row.get("CLIENT_NAME") or row.get("Client Name") or "UNKNOWN")
    action = str(row.get("BUY_SELL") or row.get("Buy/Sell") or "BUY")
    qty = _to_float(
      row.get("QUANTITY") or row.get("Quantity") or row.get("Quantity Traded")
    )
    price = _to_float(
      row.get("TRADE_PRICE")
      or row.get("Trade Price")
      or row.get("AVG_PRICE")
      or row.get("Trade Price / Wght. Avg. Price")
    )
    value = _to_float(row.get("VALUE") or row.get("Value"))
    if value is None and qty and price:
      value = qty * price
    disclosed = _parse_date(row.get("DATE") or row.get("Date"))
    source = "nse_bulk" if "bulk" in mode else "nse_block"
    source_ref = _make_ref(source, symbol, client, action, disclosed, qty, price)
    return {
      "source": source,
      "source_ref": source_ref,
      "market": "IN",
      "entity": client,
      "ticker": symbol,
      "action": action,
      "qty": qty,
      "value": value,
      "disclosed_at": disclosed,
      "source_url": "https://www.nseindia.com/market-data/block-deal",
      "raw_json": _sanitize_row_json(row),
    }


def _sanitize_row_json(row: pd.Series) -> dict | None:
  data = {}
  for k, v in row.to_dict().items():
    if v is None or (isinstance(v, float) and pd.isna(v)):
      continue
    if str(v).lower() in ("nan", "no records"):
      continue
    data[str(k)] = v if not isinstance(v, float) else (None if math.isnan(v) else v)
  return data or None


def _valid_archive_row(row: pd.Series) -> bool:
  symbol = str(row.get("SYMBOL") or row.get("Symbol") or "").strip()
  client = str(row.get("CLIENT_NAME") or row.get("Client Name") or "").strip()
  if not symbol or symbol.lower() == "nan" or "no record" in symbol.lower():
    return False
  if not client or client.lower() == "nan":
    return False
  return True


def _to_float(value: Any) -> float | None:
  if value is None or (isinstance(value, float) and pd.isna(value)):
    return None
  try:
    text = str(value).replace(",", "").strip()
    if not text or text.lower() == "nan":
      return None
    return float(text)
  except ValueError:
    return None


def _parse_date(value: Any) -> datetime:
  if isinstance(value, datetime):
    return value.astimezone(timezone.utc)
  if value is None or (isinstance(value, float) and pd.isna(value)):
    return datetime.now(IST).astimezone(timezone.utc)
  text = str(value).strip()
  if not text or text.lower() == "nan":
    return datetime.now(IST).astimezone(timezone.utc)
  for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
    try:
      parsed = datetime.strptime(text.title(), fmt)
      return parsed.replace(tzinfo=IST).astimezone(timezone.utc)
    except ValueError:
      continue
  return datetime.now(IST).astimezone(timezone.utc)


def _make_ref(
  source: str,
  symbol: str,
  client: str,
  action: str,
  disclosed: datetime,
  qty: float | None,
  price: float | None,
) -> str:
  raw = f"{source}|{symbol}|{client}|{action}|{disclosed.date()}|{qty}|{price}"
  return hashlib.sha256(raw.encode()).hexdigest()[:32]
