"""Real tests for the retention worker (worker/app.py) against a real SQLite database
— app.py's queries were written to be portable specifically so this is possible (see
the module docstring: cleanup_face_recognition_events/cleanup_face_profiles compute
each tenant's cutoff in Python rather than using Postgres's `now() - interval`).

cleanup_recordings/cleanup_snapshots are NOT tested here — they still use Postgres-only
`::interval` syntax and this service has never had a test suite before this file, so
that's a pre-existing gap, not a regression introduced now."""

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
        conn.execute(text("CREATE TABLE incidents (id TEXT PRIMARY KEY, status TEXT NOT NULL)"))
        conn.execute(text("CREATE TABLE incident_alerts (incident_id TEXT NOT NULL, alert_id TEXT NOT NULL)"))
    monkeypatch.setattr(worker_app, "engine", engine)
    return engine


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
