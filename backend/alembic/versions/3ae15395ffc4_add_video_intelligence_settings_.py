"""add video_intelligence_settings incident_cooldown_seconds

Revision ID: 3ae15395ffc4
Revises: 3417728c1c90
Create Date: 2026-09-14 14:55:17.508644

Real bug found live on the deployed VM: violation_service.py's always-incident
dispatch created a brand-new Incident every time GATE_JUMPING_DETECTED/etc. fired,
with no cooldown of its own — the same gap 3417728c1c90 just fixed for Alerts, one
layer up. See app/services/violation_service.py::_recently_had_incident.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ae15395ffc4'
down_revision: Union[str, None] = '3417728c1c90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('video_intelligence_settings', sa.Column('incident_cooldown_seconds', sa.Integer(), nullable=False, server_default='300'))


def downgrade() -> None:
    op.drop_column('video_intelligence_settings', 'incident_cooldown_seconds')
