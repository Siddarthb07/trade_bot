"""In-process paper broker with simple slippage."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from broker.base import AccountSnapshot, BrokerPosition, OrderRequest, OrderResult


class PaperBroker:
  def __init__(self, market: str, *, starting_cash: float, currency: str):
    self.market = market.upper()
    self.name = "paper"
    self.currency = currency
    self.cash = float(starting_cash)
    self.positions: dict[str, BrokerPosition] = {}

  def get_account(self) -> AccountSnapshot:
    return AccountSnapshot(
      market=self.market,
      cash=self.cash,
      buying_power=self.cash,
      currency=self.currency,
    )

  def place_order(self, order: OrderRequest) -> OrderResult:
    # Slippage: 5 bps against the trader; require limit_price or notional-implied mid
    mid = order.limit_price
    if mid is None or mid <= 0:
      if order.notional and order.qty:
        mid = order.notional / order.qty
      else:
        return OrderResult(status="rejected", broker=self.name, reject_reason="missing_price")
    slip = 0.0005
    px = mid * (1 + slip) if order.side == "buy" else mid * (1 - slip)
    cost = px * order.qty
    fee = abs(cost) * 0.0002
    if order.side == "buy":
      if cost + fee > self.cash + 1e-9:
        return OrderResult(status="rejected", broker=self.name, reject_reason="insufficient_paper_cash")
      self.cash -= cost + fee
      prev = self.positions.get(order.ticker_normalized)
      if prev:
        new_qty = prev.qty + order.qty
        avg = (prev.avg_price * prev.qty + px * order.qty) / new_qty
        self.positions[order.ticker_normalized] = BrokerPosition(order.ticker_normalized, new_qty, avg)
      else:
        self.positions[order.ticker_normalized] = BrokerPosition(order.ticker_normalized, order.qty, px)
    else:
      prev = self.positions.get(order.ticker_normalized)
      if not prev or prev.qty < order.qty - 1e-9:
        return OrderResult(status="rejected", broker=self.name, reject_reason="no_position")
      self.cash += cost - fee
      left = prev.qty - order.qty
      if left <= 1e-9:
        self.positions.pop(order.ticker_normalized, None)
      else:
        self.positions[order.ticker_normalized] = BrokerPosition(order.ticker_normalized, left, prev.avg_price)

    return OrderResult(
      status="filled",
      broker=self.name,
      broker_order_id=f"paper-{uuid.uuid4().hex[:12]}",
      fill_price=round(px, 4),
      fill_qty=order.qty,
      fee=round(fee, 4),
    )

  def cancel_order(self, broker_order_id: str) -> None:
    return None

  def list_positions(self) -> list[BrokerPosition]:
    return list(self.positions.values())

  def flatten_all(self, reason: str) -> list[OrderResult]:
    results = []
    for pos in list(self.positions.values()):
      req = OrderRequest(
        market=self.market,  # type: ignore[arg-type]
        ticker=pos.ticker,
        ticker_normalized=pos.ticker,
        side="sell",
        qty=pos.qty,
        limit_price=pos.avg_price,
        strategy_id=f"flatten:{reason}",
      )
      results.append(self.place_order(req))
    return results
