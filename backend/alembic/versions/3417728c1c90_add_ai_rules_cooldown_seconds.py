"""add ai_rules cooldown_seconds

Revision ID: 3417728c1c90
Revises: 00eb4e287db6
Create Date: 2026-09-14 14:37:53.854944

Real bug found live on the deployed VM: a rule matching a frequently-recurring event
type (PERSON_DETECTED) had no cooldown of its own at all, and created a fresh CRITICAL
alert every ~30 seconds for over an hour on a busy looping test camera. See
app/services/rule_engine.py::_recently_alerted for the fix — this migration just adds
the per-rule configurable column it reads, defaulting existing rules to 300s (5
minutes) so nothing that was already working silently starts alerting less often
without an admin choosing that.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3417728c1c90'
down_revision: Union[str, None] = '00eb4e287db6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_rules', sa.Column('cooldown_seconds', sa.Integer(), nullable=False, server_default='300'))


def downgrade() -> None:
    op.drop_column('ai_rules', 'cooldown_seconds')
