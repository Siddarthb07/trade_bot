"""Portfolio positions (manual + from-signal)

Revision ID: 002
Revises: 001
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("market", sa.String(4), nullable=False),
        sa.Column("status", sa.String(8), nullable=False, server_default="open"),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("entry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("exit_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_portfolio_positions_status", "portfolio_positions", ["status"])
    op.create_index("ix_portfolio_positions_ticker", "portfolio_positions", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_positions_ticker", "portfolio_positions")
    op.drop_index("ix_portfolio_positions_status", "portfolio_positions")
    op.drop_table("portfolio_positions")
