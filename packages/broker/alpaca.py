"""Alpaca Trading API adapter (paper or live)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from broker.base import AccountSnapshot, BrokerPosition, OrderRequest, OrderResult
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AlpacaBroker:
  market = "US"
  name = "alpaca"

  def __init__(self, *, paper: bool | None = None):
    self.paper = settings.alpaca_paper if paper is None else paper
    self.base = "https://paper-api.alpaca.markets" if self.paper else "https://api.alpaca.markets"
    self.key = settings.alpaca_api_key
    self.secret = settings.alpaca_secret_key

  def _headers(self) -> dict[str, str]:
    return {
      "APCA-API-KEY-ID": self.key,
      "APCA-API-SECRET-KEY": self.secret,
      "Content-Type": "application/json",
    }

  def _enabled(self) -> bool:
    return bool(self.key and self.secret)

  def get_account(self) -> AccountSnapshot:
    if not self._enabled():
      return AccountSnapshot(market="US", cash=0.0, buying_power=0.0, currency="USD")
    with httpx.Client(timeout=20) as client:
      r = client.get(f"{self.base}/v2/account", headers=self._headers())
      r.raise_for_status()
      data = r.json()
    return AccountSnapshot(
      market="US",
      cash=float(data.get("cash") or 0),
      buying_power=float(data.get("buying_power") or 0),
      currency="USD",
    )

  def place_order(self, order: OrderRequest) -> OrderResult:
    if not self._enabled():
      return OrderResult(status="rejected", broker=self.name, reject_reason="alpaca_keys_missing")
    # Alpaca symbol is bare ticker for US equities
    symbol = order.ticker.replace(".US", "").split(".")[0].upper()
    payload: dict[str, Any] = {
      "symbol": symbol,
      "qty": str(order.qty),
      "side": order.side,
      "type": "market",
      "time_in_force": "day",
    }
    try:
      with httpx.Client(timeout=30) as client:
        r = client.post(f"{self.base}/v2/orders", headers=self._headers(), json=payload)
        if r.status_code >= 400:
          return OrderResult(
            status="rejected",
            broker=self.name,
            reject_reason=f"alpaca_{r.status_code}:{r.text[:200]}",
          )
        data = r.json()
      # Market orders may be pending_new — treat accepted as submitted; poll once for fill
      oid = data.get("id")
      status = (data.get("status") or "submitted").lower()
      fill_price = None
      fill_qty = None
      if oid:
        with httpx.Client(timeout=20) as client:
          g = client.get(f"{self.base}/v2/orders/{oid}", headers=self._headers())
          if g.status_code == 200:
            data = g.json()
            status = (data.get("status") or status).lower()
            if data.get("filled_avg_price"):
              fill_price = float(data["filled_avg_price"])
            if data.get("filled_qty"):
              fill_qty = float(data["filled_qty"])
      mapped = "filled" if status in ("filled", "partially_filled") and fill_price else "submitted"
      if status in ("canceled", "expired", "rejected"):
        mapped = "rejected"
      return OrderResult(
        status=mapped if mapped != "submitted" or not fill_price else "filled",
        broker=self.name,
        broker_order_id=str(oid) if oid else None,
        fill_price=fill_price or order.limit_price,
        fill_qty=fill_qty or order.qty,
        fee=0.0,
        reject_reason=None if mapped != "rejected" else status,
      )
    except Exception as exc:
      logger.exception("Alpaca order failed")
      return OrderResult(status="rejected", broker=self.name, reject_reason=str(exc)[:200])

  def cancel_order(self, broker_order_id: str) -> None:
    if not self._enabled():
      return
    with httpx.Client(timeout=15) as client:
      client.delete(f"{self.base}/v2/orders/{broker_order_id}", headers=self._headers())

  def list_positions(self) -> list[BrokerPosition]:
    if not self._enabled():
      return []
    with httpx.Client(timeout=20) as client:
      r = client.get(f"{self.base}/v2/positions", headers=self._headers())
      if r.status_code >= 400:
        return []
      rows = r.json()
    return [
      BrokerPosition(
        ticker=p.get("symbol") or "",
        qty=float(p.get("qty") or 0),
        avg_price=float(p.get("avg_entry_price") or 0),
      )
      for p in rows
    ]

  def flatten_all(self, reason: str) -> list[OrderResult]:
    results = []
    for pos in self.list_positions():
      if pos.qty <= 0:
        continue
      req = OrderRequest(
        market="US",
        ticker=pos.ticker,
        ticker_normalized=pos.ticker,
        side="sell",
        qty=pos.qty,
        strategy_id=f"flatten:{reason}",
      )
      results.append(self.place_order(req))
    return results
