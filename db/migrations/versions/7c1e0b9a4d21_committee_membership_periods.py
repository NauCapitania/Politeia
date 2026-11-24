"""Committee memberships keep one row per period: unique only among current seats.

Revision ID: 7c1e0b9a4d21
Revises: 2dae99de1eeb
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c1e0b9a4d21"
down_revision: str | None = "2dae99de1eeb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_committee_memberships_committee_id_person_id_seat_kind", "committee_memberships",
                       schema="core", type_="unique")
    op.create_index("uq_committee_memberships_current", "committee_memberships",
                    ["committee_id", "person_id", "seat_kind"], unique=True, schema="core",
                    postgresql_where=sa.text("is_current"))


def downgrade() -> None:
    op.drop_index("uq_committee_memberships_current", "committee_memberships", schema="core")
    op.create_unique_constraint("uq_committee_memberships_committee_id_person_id_seat_kind", "committee_memberships",
                                ["committee_id", "person_id", "seat_kind"], schema="core")
