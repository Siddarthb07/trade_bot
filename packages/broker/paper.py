"""In-process paper broker with simple slippage."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from broker.base import AccountSnapshot, BrokerPosition, OrderRequest, OrderResult


class PaperBroker:
  def __init__(self, market: str, *, starting_cash: float, currency: str, leverage_max: float = 1.0):
    self.market = market.upper()
    self.name = "paper"
    self.currency = currency
    self.cash = float(starting_cash)
    self.initial_equity = float(starting_cash)
    self.leverage_max = max(1.0, float(leverage_max))
    self.borrowed = 0.0
    self.positions: dict[str, BrokerPosition] = {}

  def _gross_exposure(self) -> float:
    return sum(p.qty * p.avg_price for p in self.positions.values())

  def equity(self) -> float:
    return self.cash + self._gross_exposure() - self.borrowed

  def buying_power(self) -> float:
    eq = max(0.0, self.equity())
    cap = eq * self.leverage_max
    return max(0.0, cap - self._gross_exposure())

  def get_account(self) -> AccountSnapshot:
    bp = self.buying_power() if self.leverage_max > 1.0 else self.cash
    return AccountSnapshot(
      market=self.market,
      cash=self.cash,
      buying_power=bp,
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
      total = cost + fee
      if self._gross_exposure() + cost > max(0.0, self.equity()) * self.leverage_max + 1e-9:
        return OrderResult(status="rejected", broker=self.name, reject_reason="over_leverage")
      if self.leverage_max > 1.0 and total > self.cash + 1e-9:
        borrow = total - self.cash
        self.borrowed += borrow
        self.cash = 0.0
      elif total > self.cash + 1e-9:
        return OrderResult(status="rejected", broker=self.name, reject_reason="insufficient_paper_cash")
      else:
        self.cash -= total
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
      if self.borrowed > 0 and self.cash > 0:
        repay = min(self.borrowed, self.cash)
        self.borrowed -= repay
        self.cash -= repay
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

  def charge_fee(self, amount: float) -> None:
    """Apply external modeled fees (CostModel) to cash / borrow.

    Paper fills already include a tiny broker fee; India day-sim also models ~30bps RT
    via CostModel. Those must hit the book or capital_end diverges from sum(trade.pnl).
    """
    fee = float(amount or 0)
    if fee <= 0:
      return
    if self.cash >= fee - 1e-9:
      self.cash -= fee
      return
    # Levered path often leaves cash≈0 after buy — add unpaid fee to borrow.
    unpaid = fee - self.cash
    self.cash = 0.0
    self.borrowed += unpaid


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
