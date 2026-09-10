"""Retention-policy worker (section 34): periodically deletes recordings and snapshots
older than each camera's configured retention_days, skipping anything evidence-locked
(is_protected=True, section 32). Runs standalone against the same PostgreSQL database
as the backend — it does not go through the backend API since this is routine
maintenance, not a user or ai-engine action.

Deliberately implemented with plain SQLAlchemy Core (no ORM model duplication) so this
service doesn't need to stay in lockstep with backend/app/models on every migration.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] worker: %(message)s")
logger = logging.getLogger("worker")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://ezsolutions:change_me@postgres:5432/ez_camera_analytics")
RUN_INTERVAL_SECONDS = int(os.environ.get("RETENTION_CHECK_INTERVAL_SECONDS", "3600"))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def cleanup_recordings() -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT r.id, r.file_path
                FROM recordings r
                JOIN cameras c ON c.id = r.camera_id
                WHERE r.is_protected = false
                  AND r.started_at < (now() - (c.retention_days || ' days')::interval)
                """
            )
        ).fetchall()

        for row in rows:
            try:
                if row.file_path and os.path.isfile(row.file_path):
                    os.remove(row.file_path)
            except OSError as exc:
                logger.warning("Could not delete recording file %s: %s", row.file_path, exc)
            conn.execute(text("DELETE FROM recordings WHERE id = :id"), {"id": row.id})

        if rows:
            logger.info("Purged %d expired recording(s)", len(rows))


def cleanup_snapshots() -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.id, s.file_path
                FROM snapshots s
                JOIN cameras c ON c.id = s.camera_id
                WHERE s.taken_at < (now() - (c.retention_days || ' days')::interval)
                """
            )
        ).fetchall()

        for row in rows:
            try:
                if row.file_path and os.path.isfile(row.file_path):
                    os.remove(row.file_path)
            except OSError as exc:
                logger.warning("Could not delete snapshot file %s: %s", row.file_path, exc)
            conn.execute(text("DELETE FROM snapshots WHERE id = :id"), {"id": row.id})

        if rows:
            logger.info("Purged %d expired snapshot(s)", len(rows))


def main() -> None:
    logger.info("Retention worker starting — checking every %ds", RUN_INTERVAL_SECONDS)
    while True:
        try:
            cleanup_recordings()
            cleanup_snapshots()
        except Exception:
            logger.exception("Retention pass failed")
        time.sleep(RUN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
