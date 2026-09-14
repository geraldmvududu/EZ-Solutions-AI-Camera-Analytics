"""Real tests for the retention worker (worker/app.py) against a real SQLite database
— app.py's queries were written to be portable specifically so this is possible (see
the module docstring: cleanup_face_recognition_events/cleanup_face_profiles compute
each tenant's cutoff in Python rather than using Postgres's `now() - interval`).

cleanup_recordings/cleanup_snapshots are NOT tested here — they still use Postgres-only
`::interval` syntax and this service has never had a test suite before this file, so
that's a pre-existing gap, not a regression introduced now."""

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

import app as worker_app


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE face_recognition_settings (
                tenant_id TEXT PRIMARY KEY,
                event_retention_days INTEGER NOT NULL,
                face_profile_retention_days INTEGER NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE face_recognition_events (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_timestamp TIMESTAMP NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE face_profiles (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                image_reference TEXT NOT NULL,
                enrollment_date TIMESTAMP NOT NULL
            )
        """))
        conn.execute(text("CREATE TABLE alerts (id TEXT PRIMARY KEY, event_id TEXT NOT NULL)"))
        conn.execute(text("""
            CREATE TABLE incidents (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                status TEXT NOT NULL,
                evidence_clip_path TEXT,
                evidence_clip_storage_key TEXT,
                evidence_clip_size_bytes INTEGER DEFAULT 0,
                created_at TIMESTAMP,
                source_event_id TEXT
            )
        """))
        conn.execute(text("CREATE TABLE incident_alerts (incident_id TEXT NOT NULL, alert_id TEXT NOT NULL)"))
        conn.execute(text("CREATE TABLE tenants (id TEXT PRIMARY KEY, retention_tier_id TEXT)"))
        conn.execute(text("""
            CREATE TABLE retention_tiers (
                id TEXT PRIMARY KEY,
                snapshot_days INTEGER NOT NULL,
                video_evidence_days INTEGER NOT NULL,
                event_metadata_days INTEGER NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE snapshots (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                file_path TEXT,
                storage_key TEXT,
                taken_at TIMESTAMP NOT NULL,
                event_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE recordings (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                file_path TEXT,
                storage_key TEXT,
                started_at TIMESTAMP NOT NULL,
                is_protected BOOLEAN DEFAULT 0
            )
        """))
        conn.execute(text("CREATE TABLE detections (id TEXT PRIMARY KEY, snapshot_id TEXT, recording_id TEXT)"))
        conn.execute(text("""
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                occurred_at TIMESTAMP NOT NULL,
                snapshot_id TEXT,
                recording_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE cameras (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                last_heartbeat_at TIMESTAMP
            )
        """))
    monkeypatch.setattr(worker_app, "engine", engine)
    return engine


@pytest.fixture
def mock_report_event(monkeypatch):
    """check_camera_health reports real events over HTTP (POST /api/events, the same
    internal-token-authenticated endpoint ai-engine already uses) rather than inserting a
    row directly — mock that HTTP boundary the same way mock_cloud_delete mocks the S3
    boundary, and record what was reported so tests can assert on it."""
    reported = []
    monkeypatch.setattr(
        worker_app, "_report_event",
        lambda camera_id, event_type, severity, description: reported.append(
            {"camera_id": camera_id, "event_type": event_type, "severity": severity, "description": description}
        ),
    )
    return reported


@pytest.fixture
def mock_cloud_delete(monkeypatch):
    """cleanup_expired_cloud_evidence deletes the MinIO/S3 object for every purged row
    — mock the boundary the same way backend/ai-engine's test suites mock
    object_storage, so these tests never make a real network call, and record what was
    "deleted" so tests can assert on it."""
    deleted_keys = []
    monkeypatch.setattr(worker_app, "_delete_cloud_object", lambda key: deleted_keys.append(key) if key else None)
    return deleted_keys


def _insert_retention_tier(db, tenant_id: str, snapshot_days: int = 30, video_days: int = 90, event_days: int = 365) -> None:
    tier_id = _uid()
    with db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO retention_tiers (id, snapshot_days, video_evidence_days, event_metadata_days) VALUES (:id, :s, :v, :e)"
            ),
            {"id": tier_id, "s": snapshot_days, "v": video_days, "e": event_days},
        )
        conn.execute(text("INSERT INTO tenants (id, retention_tier_id) VALUES (:t, :r)"), {"t": tenant_id, "r": tier_id})


def _insert_snapshot(db, tenant_id: str, age_days: int, storage_key: str | None = "key.jpg", file_path: str | None = None) -> str:
    row_id = _uid()
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO snapshots (id, tenant_id, file_path, storage_key, taken_at) VALUES (:id, :t, :f, :k, :ts)"),
            {
                "id": row_id,
                "t": tenant_id,
                "f": file_path,
                "k": storage_key,
                "ts": datetime.now(timezone.utc) - timedelta(days=age_days),
            },
        )
    return row_id


def _insert_recording(db, tenant_id: str, age_days: int, storage_key: str | None = "clip.mp4", is_protected: bool = False) -> str:
    row_id = _uid()
    with db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO recordings (id, tenant_id, file_path, storage_key, started_at, is_protected) VALUES (:id, :t, :f, :k, :ts, :p)"
            ),
            {
                "id": row_id,
                "t": tenant_id,
                "f": None,
                "k": storage_key,
                "ts": datetime.now(timezone.utc) - timedelta(days=age_days),
                "p": is_protected,
            },
        )
    return row_id


def _insert_incident_with_clip(db, tenant_id: str, age_days: int) -> str:
    row_id = _uid()
    with db.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO incidents (id, tenant_id, status, evidence_clip_path, evidence_clip_storage_key,
                                        evidence_clip_size_bytes, created_at)
                VALUES (:id, :t, 'OPEN', :p, :k, 1000, :ts)
                """
            ),
            {"id": row_id, "t": tenant_id, "p": None, "k": "clip.mp4", "ts": datetime.now(timezone.utc) - timedelta(days=age_days)},
        )
    return row_id


def _insert_event(db, tenant_id: str, age_days: int) -> str:
    row_id = _uid()
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO events (id, tenant_id, occurred_at) VALUES (:id, :t, :ts)"),
            {"id": row_id, "t": tenant_id, "ts": datetime.now(timezone.utc) - timedelta(days=age_days)},
        )
    return row_id


def _insert_camera(db, name: str, status: str, heartbeat_age_seconds: float | None) -> str:
    row_id = _uid()
    heartbeat_at = None if heartbeat_age_seconds is None else datetime.now(timezone.utc) - timedelta(seconds=heartbeat_age_seconds)
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO cameras (id, name, status, last_heartbeat_at) VALUES (:id, :n, :s, :h)"),
            {"id": row_id, "n": name, "s": status, "h": heartbeat_at},
        )
    return row_id


def _camera_status(db, camera_id: str) -> str:
    with db.begin() as conn:
        return conn.execute(text("SELECT status FROM cameras WHERE id = :id"), {"id": camera_id}).scalar_one()


def test_check_camera_health_marks_stale_online_camera_offline(db, mock_report_event, monkeypatch):
    monkeypatch.setattr(worker_app, "CAMERA_OFFLINE_TIMEOUT_SECONDS", 30)
    stale_id = _insert_camera(db, "Stale Cam", "ONLINE", heartbeat_age_seconds=60)

    worker_app.check_camera_health()

    assert _camera_status(db, stale_id) == "OFFLINE"
    assert len(mock_report_event) == 1
    assert mock_report_event[0]["camera_id"] == stale_id
    assert mock_report_event[0]["event_type"] == "CAMERA_OFFLINE"
    assert mock_report_event[0]["severity"] == "MEDIUM"


def test_check_camera_health_leaves_fresh_heartbeat_camera_alone(db, mock_report_event, monkeypatch):
    monkeypatch.setattr(worker_app, "CAMERA_OFFLINE_TIMEOUT_SECONDS", 30)
    fresh_id = _insert_camera(db, "Fresh Cam", "ONLINE", heartbeat_age_seconds=5)

    worker_app.check_camera_health()

    assert _camera_status(db, fresh_id) == "ONLINE"
    assert mock_report_event == []


def test_check_camera_health_ignores_already_offline_cameras(db, mock_report_event, monkeypatch):
    """A camera already marked OFFLINE (e.g. by a previous check_camera_health pass, or one
    that was never started) must not report a second, redundant CAMERA_OFFLINE event every
    cycle forever."""
    monkeypatch.setattr(worker_app, "CAMERA_OFFLINE_TIMEOUT_SECONDS", 30)
    _insert_camera(db, "Already Offline", "OFFLINE", heartbeat_age_seconds=9999)

    worker_app.check_camera_health()

    assert mock_report_event == []


def test_check_camera_health_ignores_a_camera_that_has_never_heartbeated(db, mock_report_event, monkeypatch):
    """last_heartbeat_at IS NULL (a camera that's never actually run) must not be treated
    as "stale" — there's nothing to time out yet, and it isn't marked ONLINE anyway."""
    monkeypatch.setattr(worker_app, "CAMERA_OFFLINE_TIMEOUT_SECONDS", 30)
    _insert_camera(db, "Never Run", "OFFLINE", heartbeat_age_seconds=None)

    worker_app.check_camera_health()

    assert mock_report_event == []


def test_cleanup_expired_cloud_evidence_purges_old_snapshot_and_object(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, snapshot_days=30)
    old_id = _insert_snapshot(db, tenant_id, age_days=40, storage_key="tenant/old.jpg")
    new_id = _insert_snapshot(db, tenant_id, age_days=5, storage_key="tenant/new.jpg")

    worker_app.cleanup_expired_cloud_evidence()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM snapshots"))}
    assert old_id not in remaining
    assert new_id in remaining
    assert "tenant/old.jpg" in mock_cloud_delete
    assert "tenant/new.jpg" not in mock_cloud_delete


def test_cleanup_expired_cloud_evidence_nulls_event_snapshot_reference_before_delete(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, snapshot_days=30)
    old_snapshot_id = _insert_snapshot(db, tenant_id, age_days=40)
    event_id = _insert_event(db, tenant_id, age_days=1)
    with db.begin() as conn:
        conn.execute(text("UPDATE events SET snapshot_id = :s WHERE id = :e"), {"s": old_snapshot_id, "e": event_id})

    worker_app.cleanup_expired_cloud_evidence()  # must not raise despite the live reference

    with db.begin() as conn:
        event_row = conn.execute(text("SELECT snapshot_id FROM events WHERE id = :id"), {"id": event_id}).fetchone()
    assert event_row.snapshot_id is None


def test_cleanup_expired_cloud_evidence_only_purges_cloud_uploaded_recordings(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, video_days=90)
    cloud_old = _insert_recording(db, tenant_id, age_days=100, storage_key="tenant/rec.mp4")
    local_only_old = _insert_recording(db, tenant_id, age_days=100, storage_key=None)

    worker_app.cleanup_expired_cloud_evidence()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM recordings"))}
    assert cloud_old not in remaining
    assert local_only_old in remaining  # storage_key is NULL — not this function's concern


def test_cleanup_expired_cloud_evidence_skips_protected_recordings(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, video_days=90)
    protected_id = _insert_recording(db, tenant_id, age_days=100, storage_key="tenant/rec.mp4", is_protected=True)

    worker_app.cleanup_expired_cloud_evidence()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM recordings"))}
    assert protected_id in remaining


def test_cleanup_expired_cloud_evidence_clears_old_incident_evidence_clip_but_keeps_incident(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, video_days=90)
    incident_id = _insert_incident_with_clip(db, tenant_id, age_days=100)

    worker_app.cleanup_expired_cloud_evidence()

    with db.begin() as conn:
        row = conn.execute(
            text("SELECT status, evidence_clip_storage_key, evidence_clip_size_bytes FROM incidents WHERE id = :id"),
            {"id": incident_id},
        ).fetchone()
    assert row is not None  # the incident itself survives — only the clip is cleared
    assert row.evidence_clip_storage_key is None
    assert row.evidence_clip_size_bytes == 0
    assert "clip.mp4" in mock_cloud_delete


def test_cleanup_expired_cloud_evidence_deletes_quiet_events_past_cutoff(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, event_days=365)
    quiet_old = _insert_event(db, tenant_id, age_days=400)
    quiet_new = _insert_event(db, tenant_id, age_days=10)

    worker_app.cleanup_expired_cloud_evidence()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM events"))}
    assert quiet_old not in remaining
    assert quiet_new in remaining


def test_cleanup_expired_cloud_evidence_never_deletes_an_event_with_an_alert(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, event_days=365)
    alerted_event = _insert_event(db, tenant_id, age_days=400)
    with db.begin() as conn:
        conn.execute(text("INSERT INTO alerts (id, event_id) VALUES (:a, :e)"), {"a": _uid(), "e": alerted_event})

    worker_app.cleanup_expired_cloud_evidence()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM events"))}
    assert alerted_event in remaining  # never deleted — an Alert's event_id FK is NOT NULL, can't be safely orphaned


def test_cleanup_expired_cloud_evidence_never_deletes_an_event_with_a_face_recognition_event(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, event_days=365)
    recognized_event = _insert_event(db, tenant_id, age_days=400)
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO face_recognition_events (id, tenant_id, event_id, event_timestamp) VALUES (:id, :t, :e, :ts)"),
            {"id": _uid(), "t": tenant_id, "e": recognized_event, "ts": datetime.now(timezone.utc)},
        )

    worker_app.cleanup_expired_cloud_evidence()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM events"))}
    assert recognized_event in remaining


def test_cleanup_expired_cloud_evidence_nulls_incident_source_event_before_deleting_event(db, mock_cloud_delete):
    tenant_id = _uid()
    _insert_retention_tier(db, tenant_id, event_days=365)
    quiet_old = _insert_event(db, tenant_id, age_days=400)
    incident_id = _uid()
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO incidents (id, tenant_id, status, source_event_id) VALUES (:id, :t, 'OPEN', :e)"),
            {"id": incident_id, "t": tenant_id, "e": quiet_old},
        )

    worker_app.cleanup_expired_cloud_evidence()  # must not raise despite the live reference

    with db.begin() as conn:
        row = conn.execute(text("SELECT source_event_id FROM incidents WHERE id = :id"), {"id": incident_id}).fetchone()
    assert row.source_event_id is None


def test_cleanup_expired_cloud_evidence_respects_per_tenant_retention_tiers(db, mock_cloud_delete):
    tenant_short, tenant_long = _uid(), _uid()
    _insert_retention_tier(db, tenant_short, snapshot_days=10)
    _insert_retention_tier(db, tenant_long, snapshot_days=365)
    short_id = _insert_snapshot(db, tenant_short, age_days=30)
    long_id = _insert_snapshot(db, tenant_long, age_days=30)

    worker_app.cleanup_expired_cloud_evidence()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM snapshots"))}
    assert short_id not in remaining
    assert long_id in remaining


def _uid() -> str:
    return str(uuid.uuid4())


def _insert_settings(db, tenant_id: str, event_days: int = 90, profile_days: int = 365) -> None:
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO face_recognition_settings (tenant_id, event_retention_days, face_profile_retention_days) VALUES (:t, :e, :p)"),
            {"t": tenant_id, "e": event_days, "p": profile_days},
        )


def _insert_face_event(db, tenant_id: str, event_id: str, age_days: int) -> str:
    row_id = _uid()
    timestamp = datetime.now(timezone.utc) - timedelta(days=age_days)
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO face_recognition_events (id, tenant_id, event_id, event_timestamp) VALUES (:id, :t, :e, :ts)"),
            {"id": row_id, "t": tenant_id, "e": event_id, "ts": timestamp},
        )
    return row_id


def test_cleanup_face_recognition_events_deletes_only_expired_rows(db):
    tenant_id = _uid()
    _insert_settings(db, tenant_id, event_days=90)
    old_id = _insert_face_event(db, tenant_id, _uid(), age_days=100)
    new_id = _insert_face_event(db, tenant_id, _uid(), age_days=10)

    worker_app.cleanup_face_recognition_events()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM face_recognition_events"))}
    assert old_id not in remaining
    assert new_id in remaining


def test_cleanup_face_recognition_events_skips_rows_linked_to_an_open_incident(db):
    tenant_id = _uid()
    _insert_settings(db, tenant_id, event_days=90)
    event_id = _uid()
    old_id = _insert_face_event(db, tenant_id, event_id, age_days=100)

    alert_id, incident_id = _uid(), _uid()
    with db.begin() as conn:
        conn.execute(text("INSERT INTO alerts (id, event_id) VALUES (:a, :e)"), {"a": alert_id, "e": event_id})
        conn.execute(text("INSERT INTO incidents (id, status) VALUES (:i, 'OPEN')"), {"i": incident_id})
        conn.execute(text("INSERT INTO incident_alerts (incident_id, alert_id) VALUES (:i, :a)"), {"i": incident_id, "a": alert_id})

    worker_app.cleanup_face_recognition_events()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM face_recognition_events"))}
    assert old_id in remaining  # protected by the open incident despite being expired


def test_cleanup_face_recognition_events_deletes_once_incident_is_closed(db):
    tenant_id = _uid()
    _insert_settings(db, tenant_id, event_days=90)
    event_id = _uid()
    old_id = _insert_face_event(db, tenant_id, event_id, age_days=100)

    alert_id, incident_id = _uid(), _uid()
    with db.begin() as conn:
        conn.execute(text("INSERT INTO alerts (id, event_id) VALUES (:a, :e)"), {"a": alert_id, "e": event_id})
        conn.execute(text("INSERT INTO incidents (id, status) VALUES (:i, 'CLOSED')"), {"i": incident_id})
        conn.execute(text("INSERT INTO incident_alerts (incident_id, alert_id) VALUES (:i, :a)"), {"i": incident_id, "a": alert_id})

    worker_app.cleanup_face_recognition_events()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM face_recognition_events"))}
    assert old_id not in remaining


def test_cleanup_face_recognition_events_respects_per_tenant_retention(db):
    tenant_short, tenant_long = _uid(), _uid()
    _insert_settings(db, tenant_short, event_days=10)
    _insert_settings(db, tenant_long, event_days=365)
    short_id = _insert_face_event(db, tenant_short, _uid(), age_days=30)
    long_id = _insert_face_event(db, tenant_long, _uid(), age_days=30)

    worker_app.cleanup_face_recognition_events()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM face_recognition_events"))}
    assert short_id not in remaining  # 30 days old > tenant's 10-day retention
    assert long_id in remaining  # 30 days old < tenant's 365-day retention


def test_cleanup_face_profiles_deletes_expired_profile_and_image(db, tmp_path):
    tenant_id = _uid()
    _insert_settings(db, tenant_id, profile_days=365)

    old_image = tmp_path / "old.jpg"
    old_image.write_bytes(b"fake jpeg")
    new_image = tmp_path / "new.jpg"
    new_image.write_bytes(b"fake jpeg")

    old_id, new_id = _uid(), _uid()
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO face_profiles (id, tenant_id, image_reference, enrollment_date) VALUES (:id, :t, :img, :d)"),
            {"id": old_id, "t": tenant_id, "img": str(old_image), "d": datetime.now(timezone.utc) - timedelta(days=400)},
        )
        conn.execute(
            text("INSERT INTO face_profiles (id, tenant_id, image_reference, enrollment_date) VALUES (:id, :t, :img, :d)"),
            {"id": new_id, "t": tenant_id, "img": str(new_image), "d": datetime.now(timezone.utc) - timedelta(days=5)},
        )

    worker_app.cleanup_face_profiles()

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM face_profiles"))}
    assert old_id not in remaining
    assert new_id in remaining
    assert not old_image.exists()
    assert new_image.exists()


def test_cleanup_face_profiles_handles_missing_file_gracefully(db, tmp_path):
    tenant_id = _uid()
    _insert_settings(db, tenant_id, profile_days=365)
    profile_id = _uid()
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO face_profiles (id, tenant_id, image_reference, enrollment_date) VALUES (:id, :t, :img, :d)"),
            {"id": profile_id, "t": tenant_id, "img": str(tmp_path / "does_not_exist.jpg"), "d": datetime.now(timezone.utc) - timedelta(days=400)},
        )

    worker_app.cleanup_face_profiles()  # must not raise on a missing file

    with db.begin() as conn:
        remaining = {row.id for row in conn.execute(text("SELECT id FROM face_profiles"))}
    assert profile_id not in remaining


def _backdate(path, seconds_ago: float) -> None:
    old = time.time() - seconds_ago
    os.utime(path, (old, old))


@pytest.fixture
def media_roots(tmp_path, monkeypatch):
    recordings_root = tmp_path / "recordings"
    snapshots_root = tmp_path / "snapshots"
    recordings_root.mkdir()
    snapshots_root.mkdir()
    monkeypatch.setattr(worker_app, "RECORDINGS_ROOT", str(recordings_root))
    monkeypatch.setattr(worker_app, "SNAPSHOTS_ROOT", str(snapshots_root))
    return recordings_root, snapshots_root


def test_cleanup_orphaned_media_files_removes_a_file_with_no_referencing_row(db, media_roots):
    recordings_root, _ = media_roots
    orphan = recordings_root / "1789318064_eb3d016d.mp4"
    orphan.write_bytes(b"leftover video")
    _backdate(orphan, worker_app.ORPHAN_FILE_GRACE_PERIOD_SECONDS + 60)

    worker_app.cleanup_orphaned_media_files()

    assert not orphan.exists()


def test_cleanup_orphaned_media_files_keeps_a_file_referenced_by_a_recording_row(db, media_roots):
    recordings_root, _ = media_roots
    kept = recordings_root / "referenced.mp4"
    kept.write_bytes(b"real recording")
    _backdate(kept, worker_app.ORPHAN_FILE_GRACE_PERIOD_SECONDS + 60)
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO recordings (id, tenant_id, file_path, started_at, is_protected) VALUES (:id, :t, :p, :d, 0)"),
            {"id": _uid(), "t": _uid(), "p": str(kept), "d": datetime.now(timezone.utc)},
        )

    worker_app.cleanup_orphaned_media_files()

    assert kept.exists()


def test_cleanup_orphaned_media_files_keeps_a_file_referenced_by_a_snapshot_row(db, media_roots):
    _, snapshots_root = media_roots
    kept = snapshots_root / "referenced.jpg"
    kept.write_bytes(b"real snapshot")
    _backdate(kept, worker_app.ORPHAN_FILE_GRACE_PERIOD_SECONDS + 60)
    with db.begin() as conn:
        conn.execute(
            text("INSERT INTO snapshots (id, tenant_id, file_path, taken_at) VALUES (:id, :t, :p, :d)"),
            {"id": _uid(), "t": _uid(), "p": str(kept), "d": datetime.now(timezone.utc)},
        )

    worker_app.cleanup_orphaned_media_files()

    assert kept.exists()


def test_cleanup_orphaned_media_files_skips_files_within_the_grace_period(db, media_roots):
    """A file this fresh might just be one whose registering POST hasn't landed in the
    database yet — deleting it out from under an in-progress write would be worse than
    leaving a real orphan alone for one more retention cycle."""
    recordings_root, _ = media_roots
    fresh = recordings_root / "just_written.mp4"
    fresh.write_bytes(b"still being reported to the backend")

    worker_app.cleanup_orphaned_media_files()

    assert fresh.exists()


def test_cleanup_orphaned_media_files_handles_missing_directories_gracefully(db, monkeypatch, tmp_path):
    monkeypatch.setattr(worker_app, "RECORDINGS_ROOT", str(tmp_path / "does-not-exist-recordings"))
    monkeypatch.setattr(worker_app, "SNAPSHOTS_ROOT", str(tmp_path / "does-not-exist-snapshots"))

    worker_app.cleanup_orphaned_media_files()  # must not raise
