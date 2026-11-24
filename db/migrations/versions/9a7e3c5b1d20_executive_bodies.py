"""Federal Executive organs and entities from SIORG.

Revision ID: 9a7e3c5b1d20
Revises: 7c1e0b9a4d21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9a7e3c5b1d20"
down_revision: str | None = "7c1e0b9a4d21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "executive_bodies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("institution_id", sa.String(64), sa.ForeignKey("registry.institutions.id"), nullable=False),
        sa.Column("source_system_id", sa.String(64), sa.ForeignKey("registry.source_systems.id"), nullable=False),
        sa.Column("siorg_code", sa.Text(), nullable=False),
        sa.Column("parent_code", sa.Text()),
        sa.Column("unit_type", sa.String(32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("acronym", sa.Text()),
        sa.Column("legal_nature", sa.Text()),
        sa.Column("competence", sa.Text()),
        sa.Column("purpose", sa.Text()),
        sa.Column("mission", sa.Text()),
        sa.Column("legal_basis", sa.Text()),
        sa.Column("site", sa.Text()),
        sa.Column("version", sa.Text()),
        sa.Column("version_start", sa.Date()),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("attributes", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("raw_record_id", sa.Uuid(), sa.ForeignKey("ingestion.raw_records.id")),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_run_id", sa.Uuid(), sa.ForeignKey("ingestion.runs.id")),
        sa.UniqueConstraint("institution_id", "siorg_code", name="uq_executive_bodies_institution_id_siorg_code"),
        schema="core",
    )
    op.create_index("ix_executive_bodies_institution_id", "executive_bodies", ["institution_id"], schema="core")
    op.create_index("ix_executive_bodies_parent_code", "executive_bodies", ["parent_code"], schema="core")
    # Engine-only table, not exposed through the Supabase Data API: RLS on, no policies.
    op.execute("ALTER TABLE core.executive_bodies ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("executive_bodies", schema="core")
