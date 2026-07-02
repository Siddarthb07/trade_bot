"""Hold preferences table (Phase 5)

Revision ID: 003
Revises: 002
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hold_prefs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hold_display_mode", sa.String(8), nullable=False, server_default="both"),
        sa.Column("min_hold_days_filter", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exit_reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("theme_hold_multiplier", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.execute(
        sa.text(
            "INSERT INTO hold_prefs (id, hold_display_mode, min_hold_days_filter, exit_reminders_enabled, theme_hold_multiplier) "
            "VALUES (1, 'both', 0, true, 1.0)"
        )
    )


def downgrade() -> None:
    op.drop_table("hold_prefs")
