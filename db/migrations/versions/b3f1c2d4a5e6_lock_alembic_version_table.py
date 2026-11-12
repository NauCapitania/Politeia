"""Enable RLS on public.alembic_version so Supabase's Data API cannot read or write it.

Revision ID: b3f1c2d4a5e6
Revises: e85627e8e509
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b3f1c2d4a5e6"
down_revision: str | Sequence[str] | None = "e85627e8e509"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table public.alembic_version enable row level security")


def downgrade() -> None:
    op.execute("alter table public.alembic_version disable row level security")
