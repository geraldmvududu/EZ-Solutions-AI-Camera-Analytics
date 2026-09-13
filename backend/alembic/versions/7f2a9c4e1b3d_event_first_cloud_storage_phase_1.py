"""event-first cloud storage phase 1

Revision ID: 7f2a9c4e1b3d
Revises: 9c3f7a21b5d4
Create Date: 2026-09-13 18:00:00.000000

"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f2a9c4e1b3d'
down_revision: Union[str, None] = '9c3f7a21b5d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Spec section 10's own worked example values — editable afterwards only by a
# SUPER_ADMIN via GET/PUT /api/retention-tiers, never hard-coded in application code.
_RETENTION_TIERS = [
    {"name": "starter", "event_metadata_days": 30, "snapshot_days": 7, "video_evidence_days": 7},
    {"name": "business", "event_metadata_days": 90, "snapshot_days": 30, "video_evidence_days": 30},
    {"name": "professional", "event_metadata_days": 180, "snapshot_days": 90, "video_evidence_days": 90},
    {"name": "enterprise", "event_metadata_days": 365, "snapshot_days": 180, "video_evidence_days": 180},
]


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # ---- sites (section 1) ----
    op.create_table(
        'sites',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('address', sa.String(length=500), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sites_tenant_id'), 'sites', ['tenant_id'], unique=False)

    # ---- retention_tiers (section 10) — seeded, platform-wide, not tenant-scoped ----
    op.create_table(
        'retention_tiers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('event_metadata_days', sa.Integer(), nullable=False),
        sa.Column('snapshot_days', sa.Integer(), nullable=False),
        sa.Column('video_evidence_days', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_retention_tiers_name'), 'retention_tiers', ['name'], unique=True)

    retention_tiers_table = sa.table(
        'retention_tiers',
        sa.column('id', sa.Uuid()),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
        sa.column('name', sa.String()),
        sa.column('event_metadata_days', sa.Integer()),
        sa.column('snapshot_days', sa.Integer()),
        sa.column('video_evidence_days', sa.Integer()),
    )
    now = datetime.now(timezone.utc)
    tier_ids: dict[str, uuid.UUID] = {tier["name"]: uuid.uuid4() for tier in _RETENTION_TIERS}
    op.bulk_insert(
        retention_tiers_table,
        [
            {
                "id": tier_ids[tier["name"]],
                "created_at": now,
                "updated_at": now,
                "name": tier["name"],
                "event_metadata_days": tier["event_metadata_days"],
                "snapshot_days": tier["snapshot_days"],
                "video_evidence_days": tier["video_evidence_days"],
            }
            for tier in _RETENTION_TIERS
        ],
    )

    # ---- tenants.retention_tier_id (defaults every existing tenant to "starter") ----
    op.add_column('tenants', sa.Column('retention_tier_id', sa.Uuid(), nullable=True))
    if not is_sqlite:
        op.create_foreign_key('fk_tenants_retention_tier_id', 'tenants', 'retention_tiers', ['retention_tier_id'], ['id'])

    tenants_table = sa.table('tenants', sa.column('id', sa.Uuid()), sa.column('retention_tier_id', sa.Uuid()))
    connection = op.get_bind()
    connection.execute(tenants_table.update().values(retention_tier_id=tier_ids["starter"]))

    # ---- cameras.site_id (nullable) + cloud_recording_enabled, then backfill ----
    op.add_column('cameras', sa.Column('site_id', sa.Uuid(), nullable=True))
    op.add_column('cameras', sa.Column('cloud_recording_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(op.f('ix_cameras_site_id'), 'cameras', ['site_id'], unique=False)
    if not is_sqlite:
        op.create_foreign_key('fk_cameras_site_id', 'cameras', 'sites', ['site_id'], ['id'])

    # Backfill: one "Default Site" per tenant that actually has at least one camera,
    # then point every one of that tenant's cameras at it. Tenants with zero cameras
    # get no Default Site row — nothing to backfill for them. Uses SQLAlchemy Core
    # table constructs (not raw textual SQL) throughout so UUID/bool values are
    # serialized correctly by each dialect's own type compiler.
    cameras_table = sa.table('cameras', sa.column('id', sa.Uuid()), sa.column('tenant_id', sa.Uuid()), sa.column('site_id', sa.Uuid()))
    tenant_ids = [row[0] for row in connection.execute(sa.select(cameras_table.c.tenant_id).distinct()).fetchall()]
    for tenant_id in tenant_ids:
        site_id = uuid.uuid4()
        connection.execute(
            sa.table(
                'sites',
                sa.column('id', sa.Uuid()), sa.column('tenant_id', sa.Uuid()),
                sa.column('created_at', sa.DateTime(timezone=True)), sa.column('updated_at', sa.DateTime(timezone=True)),
                sa.column('name', sa.String()), sa.column('address', sa.String()),
                sa.column('timezone', sa.String()), sa.column('is_active', sa.Boolean()),
            ).insert().values(
                id=site_id, tenant_id=tenant_id, created_at=now, updated_at=now,
                name="Default Site", address="", timezone="UTC", is_active=True,
            )
        )
        connection.execute(cameras_table.update().where(cameras_table.c.tenant_id == tenant_id).values(site_id=site_id))

    # ---- snapshots: storage_key + file_size_bytes (section 9) ----
    op.add_column('snapshots', sa.Column('storage_key', sa.String(length=1000), nullable=True))
    op.add_column('snapshots', sa.Column('file_size_bytes', sa.Integer(), nullable=False, server_default='0'))

    # ---- recordings: storage_key (section 9) ----
    op.add_column('recordings', sa.Column('storage_key', sa.String(length=1000), nullable=True))

    # ---- incidents: evidence_clip_storage_key + size (section 9) ----
    op.add_column('incidents', sa.Column('evidence_clip_storage_key', sa.String(length=1000), nullable=True))
    op.add_column('incidents', sa.Column('evidence_clip_size_bytes', sa.Integer(), nullable=False, server_default='0'))

    # ---- events: review workflow + category (sections 3/13/14) ----
    event_review_status = sa.Enum('UNREVIEWED', 'REVIEWED', name='eventreviewstatus')
    event_category = sa.Enum('SECURITY', 'PEOPLE', 'VEHICLES', 'SAFETY', 'OPERATIONS', name='eventcategory')
    event_review_status.create(bind, checkfirst=True)
    event_category.create(bind, checkfirst=True)

    op.add_column('events', sa.Column('status', event_review_status, nullable=False, server_default='UNREVIEWED'))
    op.add_column('events', sa.Column('reviewed_by_user_id', sa.Uuid(), nullable=True))
    op.add_column('events', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('events', sa.Column('notes', sa.String(length=2000), nullable=False, server_default=''))
    op.add_column('events', sa.Column('event_category', event_category, nullable=False, server_default='OPERATIONS'))
    op.create_index(op.f('ix_events_status'), 'events', ['status'], unique=False)
    op.create_index(op.f('ix_events_event_category'), 'events', ['event_category'], unique=False)
    if not is_sqlite:
        op.create_foreign_key('fk_events_reviewed_by_user_id', 'events', 'users', ['reviewed_by_user_id'], ['id'])

    # Backfill event_category for existing rows using the same mapping
    # app/services/event_classification.py applies to new events going forward.
    category_by_type = {
        "TRIPWIRE_VIOLATION": "SECURITY", "INTRUSION_DETECTED": "SECURITY", "GATE_JUMPING_DETECTED": "SECURITY",
        "TAILGATING_DETECTED": "SECURITY", "RESTRICTED_AREA_VIOLATION": "SECURITY", "POTENTIAL_THEFT_DETECTED": "SECURITY",
        "UNKNOWN_FACE_DETECTED": "SECURITY",
        "PERSON_DETECTED": "PEOPLE", "LOITERING_DETECTED": "PEOPLE", "FACE_RECOGNIZED": "PEOPLE",
        "VEHICLE_DETECTED": "VEHICLES",
        "MOTION_DETECTED": "OPERATIONS", "CAMERA_OFFLINE": "OPERATIONS", "CAMERA_ONLINE": "OPERATIONS",
        "RECORDING_FAILURE": "OPERATIONS", "AI_DETECTION": "OPERATIONS",
    }
    events_table = sa.table('events', sa.column('event_type', sa.String()), sa.column('event_category', sa.String()))
    for event_type, category in category_by_type.items():
        connection.execute(events_table.update().where(events_table.c.event_type == event_type).values(event_category=category))


def downgrade() -> None:
    op.drop_index(op.f('ix_events_event_category'), table_name='events')
    op.drop_index(op.f('ix_events_status'), table_name='events')
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint('fk_events_reviewed_by_user_id', 'events', type_='foreignkey')
    op.drop_column('events', 'event_category')
    op.drop_column('events', 'notes')
    op.drop_column('events', 'reviewed_at')
    op.drop_column('events', 'reviewed_by_user_id')
    op.drop_column('events', 'status')
    sa.Enum(name='eventcategory').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='eventreviewstatus').drop(op.get_bind(), checkfirst=True)

    op.drop_column('incidents', 'evidence_clip_size_bytes')
    op.drop_column('incidents', 'evidence_clip_storage_key')

    op.drop_column('recordings', 'storage_key')

    op.drop_column('snapshots', 'file_size_bytes')
    op.drop_column('snapshots', 'storage_key')

    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint('fk_cameras_site_id', 'cameras', type_='foreignkey')
    op.drop_index(op.f('ix_cameras_site_id'), table_name='cameras')
    op.drop_column('cameras', 'cloud_recording_enabled')
    op.drop_column('cameras', 'site_id')

    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint('fk_tenants_retention_tier_id', 'tenants', type_='foreignkey')
    op.drop_column('tenants', 'retention_tier_id')

    op.drop_index(op.f('ix_retention_tiers_name'), table_name='retention_tiers')
    op.drop_table('retention_tiers')

    op.drop_index(op.f('ix_sites_tenant_id'), table_name='sites')
    op.drop_table('sites')
