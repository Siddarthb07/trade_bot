"""SQLAlchemy models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("source", "source_ref", name="uq_signals_source_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_normalized: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ticker_normalized: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    disclosed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scores: Mapped[list["SignalScore"]] = relationship(back_populates="signal")
    forward_returns: Mapped[list["ForwardReturn"]] = relationship(back_populates="signal")


class SignalScore(Base):
    __tablename__ = "signal_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    historical_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_trades: Mapped[int] = mapped_column(Integer, default=0)
    return_distribution: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    scorer_version: Mapped[str] = mapped_column(String(32), default="interim-v1")

    signal: Mapped["Signal"] = relationship(back_populates="scores")


class ForwardReturn(Base):
    __tablename__ = "forward_returns"
    __table_args__ = (UniqueConstraint("signal_id", "window", name="uq_forward_returns_signal_window"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), nullable=False, index=True)
    window: Mapped[str] = mapped_column(String(8), nullable=False)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_source: Mapped[str] = mapped_column(String(32), default="yfinance")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    signal: Mapped["Signal"] = relationship(back_populates="forward_returns")


class InvestorStat(Base):
    __tablename__ = "investor_stats"
    __table_args__ = (UniqueConstraint("entity_normalized", "market", name="uq_investor_stats_entity_market"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    market: Mapped[str] = mapped_column(String(4), nullable=False)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_trades: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_in: Mapped[int] = mapped_column(Integer, default=0)
    rows_new: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AlertLog(Base):
    __tablename__ = "alert_log"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_alert_log_dedup"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedup_key: Mapped[str] = mapped_column(String(256), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)


class AlertPrefs(Base):
    __tablename__ = "alert_prefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    min_tier: Mapped[str] = mapped_column(String(8), default="MEDIUM")
    quiet_hours_start: Mapped[int] = mapped_column(Integer, default=23)
    quiet_hours_end: Mapped[int] = mapped_column(Integer, default=8)
    market_in: Mapped[bool] = mapped_column(Boolean, default=True)
    market_us: Mapped[bool] = mapped_column(Boolean, default=True)


class HoldPrefs(Base):
    __tablename__ = "hold_prefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    hold_display_mode: Mapped[str] = mapped_column(String(8), default="both")
    min_hold_days_filter: Mapped[int] = mapped_column(Integer, default=0)
    exit_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    theme_hold_multiplier: Mapped[float] = mapped_column(Float, default=1.0)


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="open", index=True)
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
