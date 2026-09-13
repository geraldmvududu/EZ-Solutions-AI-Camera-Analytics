"""ai video intelligence phase 2 - theft detection

Revision ID: 9c3f7a21b5d4
Revises: 76bdef130907
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c3f7a21b5d4'
down_revision: Union[str, None] = '76bdef130907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- cameras: per-camera opt-in into the real multi-class (YOLOv8n) detector ----
    op.add_column('cameras', sa.Column('multi_class_detection_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))

    # ---- video_intelligence_settings: tenant-wide theft-detection kill switch ----
    op.add_column('video_intelligence_settings', sa.Column('theft_detection_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))

    # ---- new enum values on existing native Postgres ENUM types (no-op on SQLite,
    # which has no native enum type for these columns) ----
    if op.get_bind().dialect.name != "sqlite":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'POTENTIAL_THEFT_DETECTED'")
        op.execute("ALTER TYPE zonetype ADD VALUE IF NOT EXISTS 'ASSET_ZONE'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — the 2 new enum values added above are
    # left in place on downgrade (same documented tradeoff as prior migrations).
    op.drop_column('video_intelligence_settings', 'theft_detection_enabled')
    op.drop_column('cameras', 'multi_class_detection_enabled')
