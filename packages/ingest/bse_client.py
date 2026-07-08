"""BSE India bulk/block deals (free public API)."""

from __future__ import annotations

import hashlib
import io
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
BSE_HOME = "https://www.bseindia.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.bseindia.com/markets/equity/EQReports/bulknblockdeals.aspx",
}


class BSEClient:
    def __init__(self, min_interval: float = 2.5) -> None:
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
        self.session.get(BSE_HOME, timeout=30)

    def fetch_bulk_deals(self, days: int = 7) -> list[dict[str, Any]]:
        end = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=max(1, days))
        from_s = start.strftime("%d/%m/%Y")
        to_s = end.strftime("%d/%m/%Y")
        self._warmup()
        urls = [
            (
                "https://api.bseindia.com/BseIndiaAPI/api/BulkDeals/w",
                {"flag": "", "scripcode": "", "segment": "EQ", "fromdate": from_s, "todate": to_s},
            ),
            (
                "https://api.bseindia.com/BseIndiaAPI/api/BulknBlockDeals/w",
                {"flag": "0", "fromdate": from_s, "todate": to_s},
            ),
        ]
        for url, params in urls:
            try:
                self._throttle()
                resp = self.session.get(url, params=params, timeout=60)
                if resp.status_code != 200:
                    continue
                text = resp.text.strip()
                if text.startswith("[") or text.startswith("{"):
                    data = resp.json()
                    rows = data if isinstance(data, list) else data.get("Table", data.get("table", []))
                    if rows:
                        return [self._normalize_row(r) for r in rows]
                if "SCrip" in text or "Scrip" in text or "CLIENT" in text.upper():
                    return self._parse_csv(text)
            except Exception as exc:
                logger.warning("BSE bulk fetch failed %s: %s", url, exc)
        return []

    def _parse_csv(self, text: str) -> list[dict[str, Any]]:
        df = pd.read_csv(io.StringIO(text))
        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            try:
                out.append(self._normalize_row(row.to_dict()))
            except Exception:
                continue
        return out

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        symbol = str(
            row.get("Scrip Code")
            or row.get("scripcode")
            or row.get("SCripCod")
            or row.get("Scrip")
            or row.get("SYMBOL")
            or ""
        ).strip()
        name = str(row.get("Scrip Name") or row.get("scripname") or row.get("SCRIPNAME") or symbol).strip()
        client = str(
            row.get("Client Name")
            or row.get("clientname")
            or row.get("CLIENTNAME")
            or row.get("ClientName")
            or "UNKNOWN"
        ).strip()
        action_raw = str(row.get("Buy/Sell") or row.get("buysell") or row.get("BUYSELL") or "BUY").upper()
        action = "BUY" if action_raw.startswith("B") or action_raw == "P" else "SELL"
        qty = _to_float(row.get("Quantity") or row.get("quantity") or row.get("QTY"))
        price = _to_float(row.get("Price") or row.get("price") or row.get("RATE"))
        value = _to_float(row.get("Value") or row.get("value"))
        if value is None and qty and price:
            value = qty * price
        date_raw = row.get("Date") or row.get("date") or row.get("DEAL_DATE")
        disclosed = _parse_date(date_raw)
        source = "bse_bulk"
        source_ref = _make_ref(source, symbol or name, client, action, disclosed, qty, price)
        return {
            "source": source,
            "source_ref": source_ref,
            "market": "IN",
            "entity": client,
            "ticker": symbol or name[:20].replace(" ", ""),
            "action": action,
            "qty": qty,
            "value": value,
            "disclosed_at": disclosed,
            "source_url": "https://www.bseindia.com/markets/equity/EQReports/bulknblockdeals.aspx",
            "raw_json": {str(k): v for k, v in row.items() if v is not None and str(v) != "nan"},
        }


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
    text = str(value or "").strip()
    if not text:
        return datetime.now(IST).astimezone(timezone.utc)
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y"):
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
