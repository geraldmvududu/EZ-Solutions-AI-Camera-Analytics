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

cleanup_expired_cloud_evidence (Event-First Cloud Storage Phase 1, section 10) follows
the same per-tenant-cutoff-in-Python pattern, since retention here is governed by each
tenant's RetentionTier, not per-camera. It deletes MinIO/S3 objects via a small,
standalone boto3 client (this service has no app.config to import object_storage.py
from) before removing the corresponding row.
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

# Event-First Cloud Storage Phase 1 (section 9) — a minimal, standalone boto3 client
# for this service specifically (not a shared import from backend/ai-engine's
# object_storage.py, matching this file's own established convention of plain SQL/
# stdlib rather than importing backend/app models — see the module docstring). Built
# lazily so a worker deployment that never actually has a cloud-stored row to purge
# never needs real (even if fake/local) AWS credentials configured just to start up.
_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    return _s3_client


def _delete_cloud_object(storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        _get_s3_client().delete_object(Bucket=os.environ.get("AWS_S3_BUCKET", "ez-camera-evidence"), Key=storage_key)
    except Exception as exc:
        logger.warning("Could not delete cloud object %s: %s", storage_key, exc)


def _delete_local_file(file_path: str | None) -> None:
    try:
        if file_path and os.path.isfile(file_path):
            os.remove(file_path)
    except OSError as exc:
        logger.warning("Could not delete local file %s: %s", file_path, exc)


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


def cleanup_expired_cloud_evidence() -> None:
    """Event-First Cloud Storage Phase 1 (section 10): deletes cloud-stored evidence
    past each tenant's configured RetentionTier cutoff — snapshot_days,
    video_evidence_days (cloud-uploaded recordings + incident evidence clips), and
    event_metadata_days. Cutoffs are computed per-tenant in Python, the same portable
    style cleanup_face_recognition_events uses above, since retention here is a
    tenant-level RetentionTier setting rather than the per-camera retention_days that
    cleanup_recordings/cleanup_snapshots already enforce — those two are untouched and
    keep governing local-disk continuous-recording/snapshot cleanup exactly as before;
    this function only touches the newer cloud-storage-specific fields.

    A recording only counts as "cloud evidence" here (and only this function's cutoff
    applies to it) when storage_key is set — i.e. it was actually uploaded to MinIO/S3,
    per Recording's own docstring. A still-local-only CONTINUOUS recording is left
    alone; it stays governed by cleanup_recordings' existing per-camera retention_days.

    Event deletion is deliberately conservative: an Event still referenced by an Alert
    or a FaceRecognitionEvent (both NOT NULL foreign keys, meaning it was significant
    enough to alert on or match a face against) is never deleted even past its cutoff —
    there is no safe way to null those references without losing the record of what
    triggered them. Only "quiet" events (no Alert, no FaceRecognitionEvent) are
    actually purged. Incident.source_event_id/Snapshot.event_id/Detection.snapshot_id/
    Detection.recording_id/Event.snapshot_id/Event.recording_id are all nulled before
    their referenced row is deleted, since none of those foreign keys cascade."""
    with engine.begin() as conn:
        tenants = conn.execute(
            text(
                """
                SELECT t.id AS tenant_id, rt.snapshot_days, rt.video_evidence_days, rt.event_metadata_days
                FROM tenants t
                JOIN retention_tiers rt ON rt.id = t.retention_tier_id
                """
            )
        ).fetchall()

        snapshot_count = recording_count = clip_count = event_count = 0

        for tenant in tenants:
            snapshot_cutoff = datetime.now(timezone.utc) - timedelta(days=tenant.snapshot_days)
            video_cutoff = datetime.now(timezone.utc) - timedelta(days=tenant.video_evidence_days)
            event_cutoff = datetime.now(timezone.utc) - timedelta(days=tenant.event_metadata_days)

            rows = conn.execute(
                text("SELECT id, file_path, storage_key FROM snapshots WHERE tenant_id = :tenant_id AND taken_at < :cutoff"),
                {"tenant_id": tenant.tenant_id, "cutoff": snapshot_cutoff},
            ).fetchall()
            for row in rows:
                _delete_cloud_object(row.storage_key)
                _delete_local_file(row.file_path)
                conn.execute(text("UPDATE events SET snapshot_id = NULL WHERE snapshot_id = :id"), {"id": row.id})
                conn.execute(text("UPDATE detections SET snapshot_id = NULL WHERE snapshot_id = :id"), {"id": row.id})
                conn.execute(text("DELETE FROM snapshots WHERE id = :id"), {"id": row.id})
            snapshot_count += len(rows)

            rows = conn.execute(
                text(
                    """
                    SELECT id, file_path, storage_key FROM recordings
                    WHERE tenant_id = :tenant_id AND storage_key IS NOT NULL
                      AND started_at < :cutoff AND is_protected = false
                    """
                ),
                {"tenant_id": tenant.tenant_id, "cutoff": video_cutoff},
            ).fetchall()
            for row in rows:
                _delete_cloud_object(row.storage_key)
                _delete_local_file(row.file_path)
                conn.execute(text("UPDATE events SET recording_id = NULL WHERE recording_id = :id"), {"id": row.id})
                conn.execute(text("UPDATE detections SET recording_id = NULL WHERE recording_id = :id"), {"id": row.id})
                conn.execute(text("DELETE FROM recordings WHERE id = :id"), {"id": row.id})
            recording_count += len(rows)

            rows = conn.execute(
                text(
                    """
                    SELECT id, evidence_clip_path, evidence_clip_storage_key FROM incidents
                    WHERE tenant_id = :tenant_id AND evidence_clip_storage_key IS NOT NULL
                      AND created_at < :cutoff
                    """
                ),
                {"tenant_id": tenant.tenant_id, "cutoff": video_cutoff},
            ).fetchall()
            for row in rows:
                _delete_cloud_object(row.evidence_clip_storage_key)
                _delete_local_file(row.evidence_clip_path)
                conn.execute(
                    text(
                        """
                        UPDATE incidents SET evidence_clip_path = NULL, evidence_clip_storage_key = NULL,
                               evidence_clip_size_bytes = 0
                        WHERE id = :id
                        """
                    ),
                    {"id": row.id},
                )
            clip_count += len(rows)

            rows = conn.execute(
                text(
                    """
                    SELECT id FROM events e
                    WHERE e.tenant_id = :tenant_id AND e.occurred_at < :cutoff
                      AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.event_id = e.id)
                      AND NOT EXISTS (SELECT 1 FROM face_recognition_events f WHERE f.event_id = e.id)
                    """
                ),
                {"tenant_id": tenant.tenant_id, "cutoff": event_cutoff},
            ).fetchall()
            for row in rows:
                conn.execute(text("UPDATE incidents SET source_event_id = NULL WHERE source_event_id = :id"), {"id": row.id})
                conn.execute(text("UPDATE snapshots SET event_id = NULL WHERE event_id = :id"), {"id": row.id})
                conn.execute(text("DELETE FROM events WHERE id = :id"), {"id": row.id})
            event_count += len(rows)

        if snapshot_count or recording_count or clip_count or event_count:
            logger.info(
                "Purged expired cloud evidence: %d snapshot(s), %d recording(s), %d evidence clip(s), %d event(s)",
                snapshot_count,
                recording_count,
                clip_count,
                event_count,
            )


def main() -> None:
    logger.info("Retention worker starting — checking every %ds", RUN_INTERVAL_SECONDS)
    while True:
        try:
            cleanup_recordings()
            cleanup_snapshots()
            cleanup_face_recognition_events()
            cleanup_face_profiles()
            cleanup_expired_cloud_evidence()
        except Exception:
            logger.exception("Retention pass failed")
        time.sleep(RUN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
