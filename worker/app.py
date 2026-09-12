"""Retention-policy worker (section 34): periodically deletes recordings and snapshots
older than each camera's configured retention_days, skipping anything evidence-locked
(is_protected=True, section 32). Runs standalone against the same PostgreSQL database
as the backend — it does not go through the backend API since this is routine
maintenance, not a user or ai-engine action.

Deliberately implemented with plain SQLAlchemy Core (no ORM model duplication) so this
service doesn't need to stay in lockstep with backend/app/models on every migration.

cleanup_face_recognition_events/cleanup_face_profiles (Facial Recognition Phase 2,
section 15) follow the same plain-SQL style but compute each tenant's cutoff timestamp
in Python rather than with Postgres's `now() - interval` — retention here is a
per-TENANT setting (face_recognition_settings), not per-camera like recordings/
snapshots, so there's no single column to interpolate into one query across tenants
anyway. This also makes them portable to SQLite, so — unlike cleanup_recordings/
cleanup_snapshots above, which have never had automated tests since this service had
no test suite at all before this — these two are actually covered by tests/test_app.py.
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


def cleanup_face_recognition_events() -> None:
    """Deletes expired FaceRecognitionEvent rows per-tenant, per
    face_recognition_settings.event_retention_days — but never one whose underlying
    Event has an Alert still linked to a non-closed Incident (section 5/15: evidence
    tied to an open case file must survive its own retention window until the case is
    actually closed). Does not touch the linked Snapshot/Recording rows/files — those
    are cleaned up independently by cleanup_snapshots/cleanup_recordings above, per
    their own camera-level retention_days."""
    with engine.begin() as conn:
        tenants = conn.execute(text("SELECT tenant_id, event_retention_days FROM face_recognition_settings")).fetchall()
        total_deleted = 0
        for tenant in tenants:
            cutoff = datetime.now(timezone.utc) - timedelta(days=tenant.event_retention_days)
            result = conn.execute(
                text(
                    """
                    DELETE FROM face_recognition_events
                    WHERE tenant_id = :tenant_id
                      AND event_timestamp < :cutoff
                      AND NOT EXISTS (
                          SELECT 1 FROM alerts a
                          JOIN incident_alerts ia ON ia.alert_id = a.id
                          JOIN incidents i ON i.id = ia.incident_id
                          WHERE a.event_id = face_recognition_events.event_id
                            AND i.status NOT IN ('RESOLVED', 'CLOSED')
                      )
                    """
                ),
                {"tenant_id": tenant.tenant_id, "cutoff": cutoff},
            )
            total_deleted += result.rowcount

        if total_deleted:
            logger.info("Purged %d expired face recognition event(s)", total_deleted)


def cleanup_face_profiles() -> None:
    """Deletes expired FaceProfile rows (the biometric embedding + enrolled photo)
    per-tenant, per face_recognition_settings.face_profile_retention_days. The Person
    record itself is untouched — this is intentional per the original spec's
    retention table: a person's biometric template expires and must be re-enrolled
    after the configured period (365 days by default), it isn't a full account
    deletion."""
    with engine.begin() as conn:
        tenants = conn.execute(text("SELECT tenant_id, face_profile_retention_days FROM face_recognition_settings")).fetchall()
        total_deleted = 0
        for tenant in tenants:
            cutoff = datetime.now(timezone.utc) - timedelta(days=tenant.face_profile_retention_days)
            rows = conn.execute(
                text("SELECT id, image_reference FROM face_profiles WHERE tenant_id = :tenant_id AND enrollment_date < :cutoff"),
                {"tenant_id": tenant.tenant_id, "cutoff": cutoff},
            ).fetchall()

            for row in rows:
                try:
                    if row.image_reference and os.path.isfile(row.image_reference):
                        os.remove(row.image_reference)
                except OSError as exc:
                    logger.warning("Could not delete face profile image %s: %s", row.image_reference, exc)
                conn.execute(text("DELETE FROM face_profiles WHERE id = :id"), {"id": row.id})
            total_deleted += len(rows)

        if total_deleted:
            logger.info("Purged %d expired face profile(s)", total_deleted)


def main() -> None:
    logger.info("Retention worker starting — checking every %ds", RUN_INTERVAL_SECONDS)
    while True:
        try:
            cleanup_recordings()
            cleanup_snapshots()
            cleanup_face_recognition_events()
            cleanup_face_profiles()
        except Exception:
            logger.exception("Retention pass failed")
        time.sleep(RUN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
