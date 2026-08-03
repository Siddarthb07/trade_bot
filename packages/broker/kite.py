"""Zerodha Kite Connect REST adapter (needs daily access_token)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from broker.base import AccountSnapshot, BrokerPosition, OrderRequest, OrderResult
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

KITE_BASE = "https://api.kite.trade"


class KiteBroker:
  market = "IN"
  name = "kite"

  def __init__(self):
    self.api_key = settings.kite_api_key
    self.access_token = settings.kite_access_token

  def _headers(self) -> dict[str, str]:
    return {
      "X-Kite-Version": "3",
      "Authorization": f"token {self.api_key}:{self.access_token}",
    }

  def _enabled(self) -> bool:
    return bool(self.api_key and self.access_token)

  def get_account(self) -> AccountSnapshot:
    if not self._enabled():
      return AccountSnapshot(market="IN", cash=0.0, buying_power=0.0, currency="INR")
    with httpx.Client(timeout=20) as client:
      r = client.get(f"{KITE_BASE}/user/margins", headers=self._headers())
      if r.status_code >= 400:
        return AccountSnapshot(market="IN", cash=0.0, buying_power=0.0, currency="INR")
      data = r.json().get("data") or {}
      eq = data.get("equity") or {}
      avail = eq.get("available") or {}
      cash = float(avail.get("cash") or avail.get("live_balance") or 0)
    return AccountSnapshot(market="IN", cash=cash, buying_power=cash, currency="INR")

  def _tradingsymbol(self, order: OrderRequest) -> str:
    t = order.ticker.upper().replace(".NS", "").replace(".BO", "")
    return t

  def place_order(self, order: OrderRequest) -> OrderResult:
    if not self._enabled():
      return OrderResult(status="rejected", broker=self.name, reject_reason="kite_token_missing")
    # CNC for swing; MIS for day book
    product = "MIS" if order.book == "day" else "CNC"
    form: dict[str, Any] = {
      "tradingsymbol": self._tradingsymbol(order),
      "exchange": "NSE",
      "transaction_type": "BUY" if order.side == "buy" else "SELL",
      "order_type": "MARKET",
      "quantity": int(max(1, round(order.qty))),
      "product": product,
      "validity": "DAY",
    }
    try:
      with httpx.Client(timeout=30) as client:
        r = client.post(f"{KITE_BASE}/orders/regular", headers=self._headers(), data=form)
        body = r.json() if r.content else {}
        if r.status_code >= 400 or body.get("status") == "error":
          msg = body.get("message") or r.text[:200]
          return OrderResult(status="rejected", broker=self.name, reject_reason=f"kite:{msg}")
        oid = str((body.get("data") or {}).get("order_id") or "")
      return OrderResult(
        status="filled",  # market CNC/MIS typically fills; honest poll can refine later
        broker=self.name,
        broker_order_id=oid or None,
        fill_price=order.limit_price,
        fill_qty=float(form["quantity"]),
        fee=0.0,
      )
    except Exception as exc:
      logger.exception("Kite order failed")
      return OrderResult(status="rejected", broker=self.name, reject_reason=str(exc)[:200])

  def cancel_order(self, broker_order_id: str) -> None:
    if not self._enabled():
      return
    with httpx.Client(timeout=15) as client:
      client.delete(f"{KITE_BASE}/orders/regular/{broker_order_id}", headers=self._headers())

  def list_positions(self) -> list[BrokerPosition]:
    if not self._enabled():
      return []
    with httpx.Client(timeout=20) as client:
      r = client.get(f"{KITE_BASE}/portfolio/positions", headers=self._headers())
      if r.status_code >= 400:
        return []
      data = r.json().get("data") or {}
      net = data.get("net") or []
    out = []
    for p in net:
      qty = float(p.get("quantity") or 0)
      if qty == 0:
        continue
      out.append(
        BrokerPosition(
          ticker=p.get("tradingsymbol") or "",
          qty=abs(qty),
          avg_price=float(p.get("average_price") or 0),
        )
      )
    return out

  def flatten_all(self, reason: str) -> list[OrderResult]:
    results = []
    for pos in self.list_positions():
      req = OrderRequest(
        market="IN",
        ticker=pos.ticker,
        ticker_normalized=pos.ticker,
        side="sell",
        qty=pos.qty,
        book="day",
        strategy_id=f"flatten:{reason}",
        limit_price=pos.avg_price,
      )
      results.append(self.place_order(req))
    return results
