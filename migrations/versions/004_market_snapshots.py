"""Market snapshots and EOD prices from free APIs

Revision ID: 004
Revises: 003
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("snapshot_key", sa.String(128), nullable=False),
        sa.Column("market", sa.String(4), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source", "snapshot_key", name="uq_market_snapshots_source_key"),
    )
    op.create_index("ix_market_snapshots_source", "market_snapshots", ["source"])
    op.create_index("ix_market_snapshots_as_of", "market_snapshots", ["as_of"])

    op.create_table(
        "eod_prices",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("market", sa.String(4), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("ticker_normalized", sa.String(40), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("market", "ticker", "trade_date", "source", name="uq_eod_prices"),
    )
    op.create_index("ix_eod_prices_ticker_date", "eod_prices", ["ticker_normalized", "trade_date"])


def downgrade() -> None:
    op.drop_table("eod_prices")
    op.drop_table("market_snapshots")
