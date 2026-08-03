"""Persist paper/live orders and route through risk + sizing."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from broker.base import OrderRequest
from broker.paper import PaperBroker
from broker.risk import authorize, ensure_risk_state
from broker.sizing import qty_from_notional, size_notional
from core.config import get_settings
from core.models import Fill, Order, PortfolioPosition, Signal

logger = logging.getLogger(__name__)
settings = get_settings()

_PAPER: dict[str, PaperBroker] = {}


def get_paper_broker(market: str) -> PaperBroker:
  m = market.upper()
  if m not in _PAPER:
    cash = 10000.0 if m == "IN" else 100.0
    cur = "INR" if m == "IN" else "USD"
    _PAPER[m] = PaperBroker(m, starting_cash=cash, currency=cur)
  return _PAPER[m]


def get_adapter(market: str):
  """Resolve paper vs live broker for market."""
  m = market.upper()
  mode = settings.exec_mode_in if m == "IN" else settings.exec_mode_us
  if mode != "live":
    return get_paper_broker(m)
  ack = settings.exec_live_ack_in if m == "IN" else settings.exec_live_ack_us
  if not ack:
    logger.warning("Live mode without ACK for %s — falling back to paper", m)
    return get_paper_broker(m)
  if m == "US":
    from broker.alpaca import AlpacaBroker

    return AlpacaBroker()
  from broker.kite import KiteBroker

  return KiteBroker()


def _adapter_for(market: str, exec_mode: str):
  return get_adapter(market)


def submit_sized_order(
  db: Session,
  *,
  market: str,
  ticker: str,
  ticker_normalized: str,
  side: str,
  last_price: float,
  predicted_prob: float,
  strategy_id: str,
  signal_id: uuid.UUID | None = None,
  book: str = "swing",
) -> Order:
  risk = ensure_risk_state(db, market)
  # Day book uses same caps for now (isolated by book tag)
  notional, size_reason = size_notional(
    prob=predicted_prob,
    max_notional=risk.max_notional_per_trade,
    min_prob=risk.min_prob,
  )
  currency = "INR" if market.upper() == "IN" else "USD"
  if notional is None:
    order = Order(
      market=market.upper(),
      currency=currency,
      broker="none",
      ticker=ticker,
      ticker_normalized=ticker_normalized,
      side=side,
      qty=0,
      status="rejected",
      reject_reason=size_reason,
      strategy_id=strategy_id,
      predicted_prob=predicted_prob,
      signal_id=signal_id,
      book=book,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order

  allow_frac = market.upper() == "US"
  qty, qty_reason = qty_from_notional(notional, last_price, allow_fractional=allow_frac)
  if qty is None:
    order = Order(
      market=market.upper(),
      currency=currency,
      broker="none",
      ticker=ticker,
      ticker_normalized=ticker_normalized,
      side=side,
      qty=0,
      sized_notional=notional,
      status="rejected",
      reject_reason=qty_reason,
      strategy_id=strategy_id,
      predicted_prob=predicted_prob,
      signal_id=signal_id,
      book=book,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order

  ok, why, risk = authorize(db, market=market, notional=notional, book=book)
  mode = settings.exec_mode_in if market.upper() == "IN" else settings.exec_mode_us
  if not ok:
    order = Order(
      market=market.upper(),
      currency=currency,
      broker="none",
      ticker=ticker,
      ticker_normalized=ticker_normalized,
      side=side,
      qty=qty,
      notional=notional,
      sized_notional=notional,
      status="rejected",
      reject_reason=why,
      strategy_id=strategy_id,
      predicted_prob=predicted_prob,
      signal_id=signal_id,
      book=book,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order

  adapter = _adapter_for(market, mode)
  req = OrderRequest(
    market=market.upper(),  # type: ignore[arg-type]
    ticker=ticker,
    ticker_normalized=ticker_normalized,
    side=side,  # type: ignore[arg-type]
    qty=qty,
    notional=notional,
    limit_price=last_price,
    strategy_id=strategy_id,
    signal_id=str(signal_id) if signal_id else None,
    book=book,
    predicted_prob=predicted_prob,
    sized_notional=notional,
  )
  result = adapter.place_order(req)

  order = Order(
    market=market.upper(),
    currency=currency,
    broker=getattr(adapter, "name", "unknown"),
    ticker=ticker,
    ticker_normalized=ticker_normalized,
    side=side,
    qty=qty,
    notional=notional,
    sized_notional=notional,
    limit_price=last_price,
    status=result.status,
    reject_reason=result.reject_reason,
    strategy_id=strategy_id,
    predicted_prob=predicted_prob,
    signal_id=signal_id,
    broker_order_id=result.broker_order_id,
    book=book,
  )
  db.add(order)
  db.flush()

  if result.status == "filled" and result.fill_qty and result.fill_price:
    fill = Fill(
      order_id=order.id,
      qty=result.fill_qty,
      price=result.fill_price,
      fee=result.fee,
      filled_at=datetime.now(timezone.utc),
    )
    db.add(fill)
    if side == "buy":
      pos = PortfolioPosition(
        ticker=ticker,
        market=market.upper(),
        status="open",
        qty=result.fill_qty,
        entry_price=result.fill_price,
        entry_date=datetime.now(timezone.utc),
        signal_id=signal_id,
        source="auto",
        notes=f"strategy={strategy_id};book={book}",
      )
      db.add(pos)
      db.flush()
      order.position_id = pos.id

  db.commit()
  db.refresh(order)
  return order


def try_auto_trade_signal(db: Session, signal: Signal, score_prob: float | None, last_price: float | None) -> Order | None:
  """Fire under cap when session armed; uses ensemble when price history available."""
  if signal.source == "macro_theme":
    return None
  if signal.action.upper() not in ("BUY", "P", "A"):
    return None
  if last_price is None or last_price <= 0:
    return None

  strategy_id = "bulk_ml"
  prob = score_prob
  book = "swing"
  try:
    from processor.ensemble import decide_entry
    from processor.market_data import fetch_price_history

    hist = fetch_price_history(signal.ticker_normalized, days=120, db=db, market=signal.market)
    closes = [float(p["close"]) for p in hist if p.get("close")]
    decision = decide_entry(closes, bulk_prob=score_prob, ticker=signal.ticker)
    if not decision.get("fire"):
      return None
    prob = float(decision["confidence"])
    strategy_id = decision.get("strategy_id") or "ensemble"
    book = decision.get("book") or "swing"
  except Exception as exc:
    logger.debug("Ensemble fallback to bulk_ml: %s", exc)
    if score_prob is None:
      return None
    prob = float(score_prob)

  return submit_sized_order(
    db,
    market=signal.market,
    ticker=signal.ticker,
    ticker_normalized=signal.ticker_normalized,
    side="buy",
    last_price=last_price,
    predicted_prob=float(prob),
    strategy_id=strategy_id,
    signal_id=signal.id,
    book=book,
  )
