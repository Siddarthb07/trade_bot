"""Prediction events, orders/fills, risk state, strategy candidates

Revision ID: 005
Revises: 004
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    "prediction_events",
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("signal_id", UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=True, index=True),
    sa.Column("position_id", UUID(as_uuid=True), sa.ForeignKey("portfolio_positions.id"), nullable=True, index=True),
    sa.Column("order_id", UUID(as_uuid=True), nullable=True, index=True),
    sa.Column("kind", sa.String(16), nullable=False, index=True),
    sa.Column("scorer_version", sa.String(32), nullable=False),
    sa.Column("model_trained_at", sa.String(64), nullable=True),
    sa.Column("features", JSONB(), nullable=True),
    sa.Column("feature_vector", JSONB(), nullable=True),
    sa.Column("predicted_prob", sa.Float(), nullable=True),
    sa.Column("predicted_tier", sa.String(8), nullable=True),
    sa.Column("labeled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("actual_return_pct", sa.Float(), nullable=True),
    sa.Column("actual_win", sa.Boolean(), nullable=True),
    sa.Column("label_window", sa.String(8), nullable=True),
    sa.Column("labeled_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
  )
  op.create_index("ix_prediction_events_labeled", "prediction_events", ["labeled", "kind"])

  op.create_table(
    "orders",
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("market", sa.String(4), nullable=False, index=True),
    sa.Column("currency", sa.String(8), nullable=False),
    sa.Column("broker", sa.String(16), nullable=False),
    sa.Column("ticker", sa.String(32), nullable=False, index=True),
    sa.Column("ticker_normalized", sa.String(40), nullable=False),
    sa.Column("side", sa.String(8), nullable=False),
    sa.Column("qty", sa.Float(), nullable=False),
    sa.Column("notional", sa.Float(), nullable=True),
    sa.Column("limit_price", sa.Float(), nullable=True),
    sa.Column("status", sa.String(16), nullable=False, index=True),
    sa.Column("reject_reason", sa.Text(), nullable=True),
    sa.Column("strategy_id", sa.String(32), nullable=True),
    sa.Column("predicted_prob", sa.Float(), nullable=True),
    sa.Column("sized_notional", sa.Float(), nullable=True),
    sa.Column("signal_id", UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=True),
    sa.Column("position_id", UUID(as_uuid=True), sa.ForeignKey("portfolio_positions.id"), nullable=True),
    sa.Column("broker_order_id", sa.String(64), nullable=True),
    sa.Column("book", sa.String(16), nullable=False, server_default="swing"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
  )

  op.create_table(
    "fills",
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False, index=True),
    sa.Column("qty", sa.Float(), nullable=False),
    sa.Column("price", sa.Float(), nullable=False),
    sa.Column("fee", sa.Float(), nullable=False, server_default="0"),
    sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
  )

  op.create_table(
    "trade_risk_state",
    sa.Column("market", sa.String(4), primary_key=True),
    sa.Column("max_notional_per_trade", sa.Float(), nullable=False),
    sa.Column("max_open_notional", sa.Float(), nullable=False),
    sa.Column("max_open_positions", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("max_daily_loss", sa.Float(), nullable=False),
    sa.Column("max_trades_per_day", sa.Integer(), nullable=False, server_default="3"),
    sa.Column("min_prob", sa.Float(), nullable=False, server_default="0.52"),
    sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    sa.Column("ladder_stage", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("exec_mode", sa.String(8), nullable=False, server_default="paper"),
    sa.Column("session_armed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("daily_realized_pnl", sa.Float(), nullable=False, server_default="0"),
    sa.Column("daily_pnl_date", sa.Date(), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
  )

  op.create_table(
    "strategy_candidates",
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("family", sa.String(32), nullable=False),
    sa.Column("status", sa.String(16), nullable=False, server_default="candidate"),
    sa.Column("live_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("source_url", sa.Text(), nullable=True),
    sa.Column("notes", sa.Text(), nullable=True),
    sa.Column("last_report", JSONB(), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
  )

  op.execute(
    """
    INSERT INTO trade_risk_state
      (market, max_notional_per_trade, max_open_notional, max_daily_loss)
    VALUES
      ('IN', 1000, 1000, 500),
      ('US', 10, 10, 5)
    ON CONFLICT (market) DO NOTHING
    """
  )


def downgrade() -> None:
  op.drop_table("strategy_candidates")
  op.drop_table("trade_risk_state")
  op.drop_table("fills")
  op.drop_table("orders")
  op.drop_index("ix_prediction_events_labeled", "prediction_events")
  op.drop_table("prediction_events")
