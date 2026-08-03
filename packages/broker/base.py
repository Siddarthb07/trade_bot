"""Shared broker types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class OrderRequest:
  market: Literal["IN", "US"]
  ticker: str
  ticker_normalized: str
  side: Literal["buy", "sell"]
  qty: float
  notional: float | None = None
  limit_price: float | None = None
  strategy_id: str | None = None
  signal_id: str | None = None
  book: str = "swing"
  predicted_prob: float | None = None
  sized_notional: float | None = None


@dataclass
class OrderResult:
  status: str
  broker: str
  broker_order_id: str | None = None
  fill_price: float | None = None
  fill_qty: float | None = None
  fee: float = 0.0
  reject_reason: str | None = None


@dataclass
class AccountSnapshot:
  market: str
  cash: float
  buying_power: float
  currency: str


@dataclass
class BrokerPosition:
  ticker: str
  qty: float
  avg_price: float


class BrokerAdapter(Protocol):
  market: str
  name: str

  def get_account(self) -> AccountSnapshot: ...
  def place_order(self, order: OrderRequest) -> OrderResult: ...
  def cancel_order(self, broker_order_id: str) -> None: ...
  def list_positions(self) -> list[BrokerPosition]: ...
  def flatten_all(self, reason: str) -> list[OrderResult]: ...
