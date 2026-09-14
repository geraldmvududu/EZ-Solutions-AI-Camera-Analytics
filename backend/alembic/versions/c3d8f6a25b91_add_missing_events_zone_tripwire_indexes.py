"""add missing events.zone_id/tripwire_id indexes

Revision ID: c3d8f6a25b91
Revises: 8a2f5e91c4d7
Create Date: 2026-09-14 01:45:00.000000

Same bug class as the previous two migrations, found while fixing the same live
camera-delete incident: events.zone_id/tripwire_id are nullable FKs back to
zones.id/tripwires.id with no index, so deleting a camera's Zone/Tripwire rows would
force a sequential scan of the entire events table per deleted row to check for a
still-referencing event — exactly the same shape as the detection_id bug, just not
yet exercised on the live VM (that camera happened to have Zones/Tripwires with fewer
matching events than Detections had).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d8f6a25b91'
down_revision: Union[str, None] = '8a2f5e91c4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_events_zone_id'), 'events', ['zone_id'], unique=False)
    op.create_index(op.f('ix_events_tripwire_id'), 'events', ['tripwire_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_events_tripwire_id'), table_name='events')
    op.drop_index(op.f('ix_events_zone_id'), table_name='events')
