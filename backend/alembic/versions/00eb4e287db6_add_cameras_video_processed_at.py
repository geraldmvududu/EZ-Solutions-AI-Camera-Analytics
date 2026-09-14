"""add cameras video_processed_at

Revision ID: 00eb4e287db6
Revises: c3d8f6a25b91
Create Date: 2026-09-14 12:47:18.790816

Real user request: footage from a finite/looping video file kept producing
"new-looking" events every loop pass, since each crossing is genuinely >30s
apart from the last and the existing cooldowns have no way to know it's the
same underlying footage replaying. video_processed_at lets worker.py mark a
VIDEO_FILE camera (with loop_video=False) as done once it reaches real
end-of-file, at which point is_active is also set False so the camera stops
being picked up for analysis entirely — see Camera.video_processed_at's own
docstring in app/models/camera.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00eb4e287db6'
down_revision: Union[str, None] = 'c3d8f6a25b91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cameras', sa.Column('video_processed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('cameras', 'video_processed_at')
