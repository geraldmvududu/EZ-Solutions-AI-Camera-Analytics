"""face recognition & identity analytics

Revision ID: 6619233f6706
Revises: 1b156805d0ee
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6619233f6706'
down_revision: Union[str, None] = '1b156805d0ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- Camera face-recognition config (mirrors ai_enabled/confidence_threshold) ----
    op.add_column('cameras', sa.Column('face_recognition_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('cameras', sa.Column('face_recognition_threshold', sa.Float(), nullable=True))
    op.add_column('cameras', sa.Column('face_operating_hours_start', sa.String(length=5), nullable=False, server_default=''))
    op.add_column('cameras', sa.Column('face_operating_hours_end', sa.String(length=5), nullable=False, server_default=''))

    # ---- New enum values on existing native Postgres ENUM types ----
    # SQLite has no native enum type for these columns (SQLAlchemy's Enum only
    # creates a CHECK constraint when create_constraint=True, which this project does
    # not set — see app/models/event.py/zone.py), so there is nothing to alter there;
    # this section only applies to Postgres. Adding a value with ALTER TYPE is safe to
    # run inside a normal migration transaction as long as the new value isn't used
    # in the same transaction, which it isn't here.
    if op.get_bind().dialect.name != "sqlite":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'FACE_RECOGNIZED'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'UNKNOWN_FACE_DETECTED'")
        op.execute("ALTER TYPE zonetype ADD VALUE IF NOT EXISTS 'FACE_DETECTION'")
        op.execute("ALTER TYPE zonetype ADD VALUE IF NOT EXISTS 'FACE_EXCLUSION'")

    # ---- persons ----
    op.create_table(
        'persons',
        sa.Column('external_reference', sa.String(length=100), nullable=False),
        sa.Column('first_name', sa.String(length=150), nullable=False),
        sa.Column('last_name', sa.String(length=150), nullable=False),
        sa.Column('category', sa.Enum('EMPLOYEE', 'CONTRACTOR', 'VISITOR', 'AUTHORIZED_PERSON', 'WATCHLIST', name='personcategory'), nullable=False),
        sa.Column('department', sa.String(length=150), nullable=False),
        sa.Column('notes', sa.String(length=2000), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'SUSPENDED', 'DELETED', name='personstatus'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_persons_external_reference'), 'persons', ['external_reference'], unique=False)
    op.create_index(op.f('ix_persons_category'), 'persons', ['category'], unique=False)
    op.create_index(op.f('ix_persons_status'), 'persons', ['status'], unique=False)
    op.create_index(op.f('ix_persons_tenant_id'), 'persons', ['tenant_id'], unique=False)

    # ---- face_profiles ----
    op.create_table(
        'face_profiles',
        sa.Column('person_id', sa.Uuid(), nullable=False),
        sa.Column('embedding_encrypted', sa.Text(), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('image_reference', sa.String(length=1000), nullable=False),
        sa.Column('quality_score', sa.Float(), nullable=False),
        sa.Column('enrollment_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'SUSPENDED', 'DELETED', name='faceprofilestatus'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['person_id'], ['persons.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_face_profiles_person_id'), 'face_profiles', ['person_id'], unique=False)
    op.create_index(op.f('ix_face_profiles_status'), 'face_profiles', ['status'], unique=False)
    op.create_index(op.f('ix_face_profiles_tenant_id'), 'face_profiles', ['tenant_id'], unique=False)

    # ---- face_recognition_events ----
    op.create_table(
        'face_recognition_events',
        sa.Column('event_id', sa.Uuid(), nullable=False),
        sa.Column('camera_id', sa.Uuid(), nullable=False),
        sa.Column('person_id', sa.Uuid(), nullable=True),
        sa.Column('face_profile_id', sa.Uuid(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('recognition_status', sa.Enum('RECOGNIZED', 'UNKNOWN', 'LOW_CONFIDENCE', name='recognitionstatus'), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('event_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('snapshot_id', sa.Uuid(), nullable=True),
        sa.Column('recording_id', sa.Uuid(), nullable=True),
        sa.Column('reviewed', sa.Boolean(), nullable=False),
        sa.Column('review_decision', sa.String(length=30), nullable=False),
        sa.Column('review_notes', sa.String(length=2000), nullable=False),
        sa.Column('reviewed_by', sa.Uuid(), nullable=True),
        sa.Column('review_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ),
        sa.ForeignKeyConstraint(['person_id'], ['persons.id'], ),
        sa.ForeignKeyConstraint(['face_profile_id'], ['face_profiles.id'], ),
        sa.ForeignKeyConstraint(['snapshot_id'], ['snapshots.id'], ),
        sa.ForeignKeyConstraint(['recording_id'], ['recordings.id'], ),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_face_recognition_events_event_id'), 'face_recognition_events', ['event_id'], unique=False)
    op.create_index(op.f('ix_face_recognition_events_camera_id'), 'face_recognition_events', ['camera_id'], unique=False)
    op.create_index(op.f('ix_face_recognition_events_person_id'), 'face_recognition_events', ['person_id'], unique=False)
    op.create_index(op.f('ix_face_recognition_events_recognition_status'), 'face_recognition_events', ['recognition_status'], unique=False)
    op.create_index(op.f('ix_face_recognition_events_event_timestamp'), 'face_recognition_events', ['event_timestamp'], unique=False)
    op.create_index(op.f('ix_face_recognition_events_reviewed'), 'face_recognition_events', ['reviewed'], unique=False)
    op.create_index(op.f('ix_face_recognition_events_tenant_id'), 'face_recognition_events', ['tenant_id'], unique=False)

    # ---- face_recognition_settings (one row per tenant) ----
    op.create_table(
        'face_recognition_settings',
        sa.Column('facial_recognition_enabled', sa.Boolean(), nullable=False),
        sa.Column('unknown_face_detection_enabled', sa.Boolean(), nullable=False),
        sa.Column('default_match_threshold', sa.Float(), nullable=False),
        sa.Column('multi_frame_confirmation_enabled', sa.Boolean(), nullable=False),
        sa.Column('liveness_detection_enabled', sa.Boolean(), nullable=False),
        sa.Column('recognition_cooldown_seconds', sa.Integer(), nullable=False),
        sa.Column('max_events_per_person_camera_per_hour', sa.Integer(), nullable=False),
        sa.Column('event_retention_days', sa.Integer(), nullable=False),
        sa.Column('snapshot_retention_days', sa.Integer(), nullable=False),
        sa.Column('face_profile_retention_days', sa.Integer(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_face_recognition_settings_tenant_id'), 'face_recognition_settings', ['tenant_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_face_recognition_settings_tenant_id'), table_name='face_recognition_settings')
    op.drop_table('face_recognition_settings')

    op.drop_index(op.f('ix_face_recognition_events_tenant_id'), table_name='face_recognition_events')
    op.drop_index(op.f('ix_face_recognition_events_reviewed'), table_name='face_recognition_events')
    op.drop_index(op.f('ix_face_recognition_events_event_timestamp'), table_name='face_recognition_events')
    op.drop_index(op.f('ix_face_recognition_events_recognition_status'), table_name='face_recognition_events')
    op.drop_index(op.f('ix_face_recognition_events_person_id'), table_name='face_recognition_events')
    op.drop_index(op.f('ix_face_recognition_events_camera_id'), table_name='face_recognition_events')
    op.drop_index(op.f('ix_face_recognition_events_event_id'), table_name='face_recognition_events')
    op.drop_table('face_recognition_events')

    op.drop_index(op.f('ix_face_profiles_tenant_id'), table_name='face_profiles')
    op.drop_index(op.f('ix_face_profiles_status'), table_name='face_profiles')
    op.drop_index(op.f('ix_face_profiles_person_id'), table_name='face_profiles')
    op.drop_table('face_profiles')

    op.drop_index(op.f('ix_persons_tenant_id'), table_name='persons')
    op.drop_index(op.f('ix_persons_status'), table_name='persons')
    op.drop_index(op.f('ix_persons_category'), table_name='persons')
    op.drop_index(op.f('ix_persons_external_reference'), table_name='persons')
    op.drop_table('persons')

    # Postgres has no ALTER TYPE ... DROP VALUE — the 4 new enum values added in
    # upgrade() are intentionally left in place on downgrade (harmless if unused).

    op.drop_column('cameras', 'face_operating_hours_end')
    op.drop_column('cameras', 'face_operating_hours_start')
    op.drop_column('cameras', 'face_recognition_threshold')
    op.drop_column('cameras', 'face_recognition_enabled')

    if op.get_bind().dialect.name != "sqlite":
        op.execute("DROP TYPE IF EXISTS faceprofilestatus")
        op.execute("DROP TYPE IF EXISTS recognitionstatus")
        op.execute("DROP TYPE IF EXISTS personcategory")
        op.execute("DROP TYPE IF EXISTS personstatus")
