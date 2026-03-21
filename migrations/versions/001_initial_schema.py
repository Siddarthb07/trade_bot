"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("market", sa.String(4), nullable=False),
        sa.Column("entity", sa.String(256), nullable=False),
        sa.Column("entity_normalized", sa.String(256), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("ticker_normalized", sa.String(40), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("disclosed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source", "source_ref", name="uq_signals_source_ref"),
    )
    op.create_index("ix_signals_source", "signals", ["source"])
    op.create_index("ix_signals_market", "signals", ["market"])
    op.create_index("ix_signals_entity_normalized", "signals", ["entity_normalized"])
    op.create_index("ix_signals_ticker", "signals", ["ticker"])
    op.create_index("ix_signals_disclosed_at", "signals", ["disclosed_at"])

    op.create_table(
        "signal_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("tier", sa.String(8), nullable=False),
        sa.Column("historical_win_rate", sa.Float(), nullable=True),
        sa.Column("n_trades", sa.Integer(), server_default="0"),
        sa.Column("return_distribution", postgresql.JSONB(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("scorer_version", sa.String(32), server_default="interim-v1"),
    )
    op.create_index("ix_signal_scores_signal_id", "signal_scores", ["signal_id"])
    op.create_index("ix_signal_scores_tier", "signal_scores", ["tier"])

    op.create_table(
        "forward_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("window", sa.String(8), nullable=False),
        sa.Column("return_pct", sa.Float(), nullable=True),
        sa.Column("price_source", sa.String(32), server_default="yfinance"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("signal_id", "window", name="uq_forward_returns_signal_window"),
    )
    op.create_index("ix_forward_returns_signal_id", "forward_returns", ["signal_id"])

    op.create_table(
        "investor_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_normalized", sa.String(256), nullable=False),
        sa.Column("market", sa.String(4), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("median_return", sa.Float(), nullable=True),
        sa.Column("n_trades", sa.Integer(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("entity_normalized", "market", name="uq_investor_stats_entity_market"),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_name", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_in", sa.Integer(), server_default="0"),
        sa.Column("rows_new", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(16), server_default="running"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_ingestion_runs_job_name", "ingestion_runs", ["job_name"])

    op.create_table(
        "alert_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dedup_key", sa.String(256), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retries", sa.Integer(), server_default="0"),
        sa.UniqueConstraint("dedup_key", name="uq_alert_log_dedup"),
    )

    op.create_table(
        "alert_prefs",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("min_tier", sa.String(8), server_default="MEDIUM"),
        sa.Column("quiet_hours_start", sa.Integer(), server_default="23"),
        sa.Column("quiet_hours_end", sa.Integer(), server_default="8"),
        sa.Column("market_in", sa.Boolean(), server_default="true"),
        sa.Column("market_us", sa.Boolean(), server_default="true"),
    )
    op.execute(
        "INSERT INTO alert_prefs (id, min_tier, quiet_hours_start, quiet_hours_end, market_in, market_us) "
        "VALUES (1, 'MEDIUM', 23, 8, true, true) ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("alert_prefs")
    op.drop_table("alert_log")
    op.drop_table("ingestion_runs")
    op.drop_table("investor_stats")
    op.drop_table("forward_returns")
    op.drop_table("signal_scores")
    op.drop_table("signals")
