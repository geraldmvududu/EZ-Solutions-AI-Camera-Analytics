"""ai video intelligence phase 1

Revision ID: 76bdef130907
Revises: 6619233f6706
Create Date: 2026-09-12 19:05:15.527806

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76bdef130907'
down_revision: Union[str, None] = '6619233f6706'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- tripwires: gate-jump / tailgating opt-in flags (sections 4/8) ----
    op.add_column('tripwires', sa.Column('gate_jump_detection_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('tripwires', sa.Column('tailgating_detection_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('tripwires', sa.Column('tailgating_window_seconds', sa.Integer(), nullable=False, server_default='5'))

    # ---- incidents: risk score / review workflow / evidence clip (sections 19/26/33) ----
    op.add_column('incidents', sa.Column('incident_type', sa.String(length=100), nullable=False, server_default=''))
    op.add_column('incidents', sa.Column('confidence', sa.Float(), nullable=True))
    op.add_column('incidents', sa.Column('risk_score', sa.Integer(), nullable=True))
    op.add_column('incidents', sa.Column('requires_human_review', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('incidents', sa.Column('review_decision', sa.String(length=50), nullable=False, server_default=''))
    op.add_column('incidents', sa.Column('evidence_clip_path', sa.String(length=500), nullable=True))
    op.add_column('incidents', sa.Column('source_event_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_incidents_incident_type'), 'incidents', ['incident_type'], unique=False)
    # SQLite can't ALTER TABLE ADD CONSTRAINT outside of Alembic's batch mode (same
    # documented limitation as the circular FK columns in the initial migration) — the
    # column and its data are identical either way, only the DB-level FK enforcement
    # differs, and this project never relied on SQLite enforcing it.
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key('fk_incidents_source_event_id', 'incidents', 'events', ['source_event_id'], ['id'], use_alter=True)

    # ---- new enum values on existing native Postgres ENUM types ----
    # SQLite has no native enum type for these columns (see the face-recognition
    # migration's identical note above the equivalent block) — this only applies to
    # Postgres. Safe to run inside a normal migration transaction since the new value
    # isn't used in the same transaction.
    if op.get_bind().dialect.name != "sqlite":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'GATE_JUMPING_DETECTED'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'TAILGATING_DETECTED'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'RESTRICTED_AREA_VIOLATION'")
        op.execute("ALTER TYPE zonetype ADD VALUE IF NOT EXISTS 'RESTRICTED_AREA'")

    # ---- video_intelligence_settings (section 35) — one row per tenant, seeded on
    # first use by app/api/routes/video_intelligence.py::_get_or_create_settings ----
    op.create_table(
        'video_intelligence_settings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('gate_jumping_enabled', sa.Boolean(), nullable=False),
        sa.Column('tailgating_enabled', sa.Boolean(), nullable=False),
        sa.Column('restricted_area_enabled', sa.Boolean(), nullable=False),
        sa.Column('min_confidence', sa.Float(), nullable=False),
        sa.Column('pre_event_seconds', sa.Integer(), nullable=False),
        sa.Column('post_event_seconds', sa.Integer(), nullable=False),
        sa.Column('business_hours_start', sa.String(length=5), nullable=False),
        sa.Column('business_hours_end', sa.String(length=5), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
    )
    op.create_index(op.f('ix_video_intelligence_settings_tenant_id'), 'video_intelligence_settings', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_video_intelligence_settings_tenant_id'), table_name='video_intelligence_settings')
    op.drop_table('video_intelligence_settings')

    # Postgres has no ALTER TYPE ... DROP VALUE — the 4 new enum values added above
    # are left in place on downgrade (same documented tradeoff as the face-recognition
    # migration's downgrade).

    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint('fk_incidents_source_event_id', 'incidents', type_='foreignkey')
    op.drop_column('incidents', 'source_event_id')
    op.drop_index(op.f('ix_incidents_incident_type'), table_name='incidents')
    op.drop_column('incidents', 'evidence_clip_path')
    op.drop_column('incidents', 'review_decision')
    op.drop_column('incidents', 'requires_human_review')
    op.drop_column('incidents', 'risk_score')
    op.drop_column('incidents', 'confidence')
    op.drop_column('incidents', 'incident_type')

    op.drop_column('tripwires', 'tailgating_window_seconds')
    op.drop_column('tripwires', 'tailgating_detection_enabled')
    op.drop_column('tripwires', 'gate_jump_detection_enabled')
