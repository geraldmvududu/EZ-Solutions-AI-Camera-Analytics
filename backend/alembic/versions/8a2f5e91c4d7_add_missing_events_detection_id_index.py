"""add missing events.detection_id index

Revision ID: 8a2f5e91c4d7
Revises: 40b1be56b718
Create Date: 2026-09-14 01:15:00.000000

Real performance bug found live on a deployed VM, one level worse than the
snapshot_id/recording_id indexes the previous migration added: deleting a camera
with 137,927 real detections took over 3 minutes (still running when this migration
was written) because `events.detection_id` — a nullable FK back to detections.id,
part of the events/detections/snapshots/recordings reference cycle — had no index.
Every one of those 137,927 `DELETE FROM detections` rows required Postgres to check
whether any event still referenced it, and with no index on events.detection_id that
check falls back to a sequential scan of the entire events table, repeated once per
deleted detection row.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8a2f5e91c4d7'
down_revision: Union[str, None] = '40b1be56b718'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_events_detection_id'), 'events', ['detection_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_events_detection_id'), table_name='events')
