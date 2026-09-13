"""add missing fk indexes on snapshot/recording/alert/event references

Revision ID: 40b1be56b718
Revises: 7f2a9c4e1b3d
Create Date: 2026-09-14 00:22:06.203555

Real performance bug found live on a deployed VM: none of the snapshot_id/
recording_id foreign key columns on alerts/detections/events/face_recognition_events
(nor notifications.alert_id, incidents.camera_id, incidents.source_event_id) were
indexed. A bulk DELETE FROM snapshots with ~27k rows — each requiring Postgres to scan
every referencing table to verify the FK constraint — took over 20 minutes as a result
(confirmed via pg_stat_activity: no locks, no blocking, just a sequential scan per
row). Every other autogenerate diff against this dev SQLite DB (FK/enum-type "changes")
is a known reflection artifact of SQLite's limited ALTER/FK support — see this
project's other hand-written migrations — and is deliberately excluded here; this
migration adds only the seven missing indexes.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '40b1be56b718'
down_revision: Union[str, None] = '7f2a9c4e1b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_alerts_snapshot_id'), 'alerts', ['snapshot_id'], unique=False)
    op.create_index(op.f('ix_alerts_recording_id'), 'alerts', ['recording_id'], unique=False)
    op.create_index(op.f('ix_detections_snapshot_id'), 'detections', ['snapshot_id'], unique=False)
    op.create_index(op.f('ix_detections_recording_id'), 'detections', ['recording_id'], unique=False)
    op.create_index(op.f('ix_events_snapshot_id'), 'events', ['snapshot_id'], unique=False)
    op.create_index(op.f('ix_events_recording_id'), 'events', ['recording_id'], unique=False)
    op.create_index(op.f('ix_face_recognition_events_snapshot_id'), 'face_recognition_events', ['snapshot_id'], unique=False)
    op.create_index(op.f('ix_face_recognition_events_recording_id'), 'face_recognition_events', ['recording_id'], unique=False)
    op.create_index(op.f('ix_notifications_alert_id'), 'notifications', ['alert_id'], unique=False)
    op.create_index(op.f('ix_incidents_camera_id'), 'incidents', ['camera_id'], unique=False)
    op.create_index(op.f('ix_incidents_source_event_id'), 'incidents', ['source_event_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_incidents_source_event_id'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_camera_id'), table_name='incidents')
    op.drop_index(op.f('ix_notifications_alert_id'), table_name='notifications')
    op.drop_index(op.f('ix_face_recognition_events_recording_id'), table_name='face_recognition_events')
    op.drop_index(op.f('ix_face_recognition_events_snapshot_id'), table_name='face_recognition_events')
    op.drop_index(op.f('ix_events_recording_id'), table_name='events')
    op.drop_index(op.f('ix_events_snapshot_id'), table_name='events')
    op.drop_index(op.f('ix_detections_recording_id'), table_name='detections')
    op.drop_index(op.f('ix_detections_snapshot_id'), table_name='detections')
    op.drop_index(op.f('ix_alerts_recording_id'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_snapshot_id'), table_name='alerts')
