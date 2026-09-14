"""master development prompt phase 1 - license plate reading (anpr)

Revision ID: 4a9d3f7c2e5b
Revises: 3f8a2c5e9b1d
Create Date: 2026-09-15 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4a9d3f7c2e5b'
down_revision: Union[str, None] = '3f8a2c5e9b1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cameras', sa.Column('plate_recognition_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        'vehicle_watchlists',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('plate_text', sa.String(length=20), nullable=False, index=True),
        sa.Column(
            'status',
            sa.Enum('AUTHORIZED', 'UNAUTHORIZED', 'WATCHLIST', 'BLACKLISTED', name='vehiclewatchliststatus'),
            nullable=False,
        ),
        sa.Column('description', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('notes', sa.String(length=2000), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_vehicle_watchlists_status', 'vehicle_watchlists', ['status'])

    op.create_table(
        'license_plates',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('event_id', sa.Uuid(), sa.ForeignKey('events.id'), nullable=False, index=True),
        sa.Column('camera_id', sa.Uuid(), sa.ForeignKey('cameras.id'), nullable=False, index=True),
        sa.Column('watchlist_id', sa.Uuid(), sa.ForeignKey('vehicle_watchlists.id'), nullable=True, index=True),
        sa.Column('plate_text', sa.String(length=20), nullable=False, index=True),
        sa.Column('vehicle_type', sa.String(length=30), nullable=False, server_default=''),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('tracking_id', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('snapshot_id', sa.Uuid(), sa.ForeignKey('snapshots.id'), nullable=True, index=True),
        sa.Column('recording_id', sa.Uuid(), sa.ForeignKey('recordings.id'), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # New enum values on the existing native Postgres ENUM type (no-op on SQLite).
    if op.get_bind().dialect.name != "sqlite":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'LICENSE_PLATE_DETECTED'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'VEHICLE_WATCHLIST_MATCH'")


def downgrade() -> None:
    op.drop_table('license_plates')
    op.drop_index('ix_vehicle_watchlists_status', table_name='vehicle_watchlists')
    op.drop_table('vehicle_watchlists')
    if op.get_bind().dialect.name != "sqlite":
        op.execute("DROP TYPE IF EXISTS vehiclewatchliststatus")
    op.drop_column('cameras', 'plate_recognition_enabled')
