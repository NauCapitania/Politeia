"""Keep the date of a process step as the source gives it (month-only dates such as "2026-01").

Revision ID: c4d8e1f2a3b5
Revises: bf3e762c27c6
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8e1f2a3b5"
down_revision: str | None = "bf3e762c27c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("steps", sa.Column("date_label", sa.Text()), schema="process")


def downgrade() -> None:
    op.drop_column("steps", "date_label", schema="process")
