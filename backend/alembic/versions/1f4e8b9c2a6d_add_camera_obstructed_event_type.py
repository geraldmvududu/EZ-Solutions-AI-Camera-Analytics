"""master development prompt phase 1 - camera obstructed event type

Revision ID: 1f4e8b9c2a6d
Revises: 3ae15395ffc4
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1f4e8b9c2a6d'
down_revision: Union[str, None] = '3ae15395ffc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New enum value on the existing native Postgres ENUM type (no-op on SQLite, which
    # has no native enum type for this column) — see ai-engine/app/core/camera_health.py
    # for the real, disclosed obstruction heuristic this event type reports.
    if op.get_bind().dialect.name != "sqlite":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'CAMERA_OBSTRUCTED'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — the enum value added above is left in
    # place on downgrade (same documented tradeoff as prior migrations, e.g.
    # 9c3f7a21b5d4_ai_video_intelligence_phase_2.py).
    pass
