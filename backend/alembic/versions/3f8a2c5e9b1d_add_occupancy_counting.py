"""master development prompt phase 1 - crowd/occupancy counting

Revision ID: 3f8a2c5e9b1d
Revises: 2c7d1f9a4e8b
Create Date: 2026-09-15 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3f8a2c5e9b1d'
down_revision: Union[str, None] = '2c7d1f9a4e8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tripwires', sa.Column('occupancy_counting_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('cameras', sa.Column('current_occupancy', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('cameras', sa.Column('max_occupancy', sa.Integer(), nullable=True))

    # New enum value on the existing native Postgres ENUM type (no-op on SQLite).
    if op.get_bind().dialect.name != "sqlite":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'MAXIMUM_OCCUPANCY_EXCEEDED'")


def downgrade() -> None:
    op.drop_column('cameras', 'max_occupancy')
    op.drop_column('cameras', 'current_occupancy')
    op.drop_column('tripwires', 'occupancy_counting_enabled')
