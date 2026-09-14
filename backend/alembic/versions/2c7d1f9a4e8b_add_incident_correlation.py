"""master development prompt phase 1 - multi-event incident correlation

Revision ID: 2c7d1f9a4e8b
Revises: 1f4e8b9c2a6d
Create Date: 2026-09-15 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2c7d1f9a4e8b'
down_revision: Union[str, None] = '1f4e8b9c2a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('incidents', sa.Column('correlation_key', sa.String(length=300), nullable=True))
    op.create_index('ix_incidents_correlation_key', 'incidents', ['correlation_key'])

    op.create_table(
        'incident_events',
        sa.Column('incident_id', sa.Uuid(), sa.ForeignKey('incidents.id'), primary_key=True),
        sa.Column('event_id', sa.Uuid(), sa.ForeignKey('events.id'), primary_key=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column(
        'video_intelligence_settings',
        sa.Column('correlation_window_seconds', sa.Integer(), nullable=False, server_default='120'),
    )


def downgrade() -> None:
    op.drop_column('video_intelligence_settings', 'correlation_window_seconds')
    op.drop_table('incident_events')
    op.drop_index('ix_incidents_correlation_key', table_name='incidents')
    op.drop_column('incidents', 'correlation_key')
