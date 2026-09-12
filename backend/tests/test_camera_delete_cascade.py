"""Deleting a camera that already has real activity against it (section 57's data
model) used to raise an unhandled foreign-key violation on Postgres — SQLite (used by
every other test in this suite) never enforces the FKs pointing at cameras.id, so a
naive db.delete(camera) "worked" in every local test run but failed for real once a
camera had dependent rows. These tests build that real dependent data directly against
the DB (matching the shape ai-engine/the rule engine actually produce) rather than
relying on SQLite's leniency to mask the bug the way the original code accidentally did."""

import uuid
from datetime import datetime, timezone

from app.models.alert import Alert
from app.models.detection import Detection, ObjectType
from app.models.event import Event, EventSeverity, EventType
from app.models.face_profile import FaceProfile
from app.models.face_recognition_event import FaceRecognitionEvent, RecognitionStatus
from app.models.person import Person, PersonCategory
from app.models.recording import Recording, RecordingTrigger
from app.models.rule import AIRule
from app.models.snapshot import Snapshot
from app.models.tripwire import Tripwire
from app.models.zone import Zone, ZoneType
from tests.conftest import auth_headers, login


def test_delete_camera_with_full_real_dependent_data(client, db_session, admin_user, tenant):
    token = login(client, admin_user.email)
    camera_id = uuid.UUID(
        client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()["id"]
    )

    detection = Detection(
        tenant_id=tenant.id, camera_id=camera_id, object_type=ObjectType.PERSON, confidence=0.9,
        bbox_x=0.1, bbox_y=0.1, bbox_width=0.2, bbox_height=0.4, tracking_id=1,
        detected_at=datetime.now(timezone.utc),
    )
    snapshot = Snapshot(tenant_id=tenant.id, camera_id=camera_id, file_path="/tmp/does-not-exist.jpg", taken_at=datetime.now(timezone.utc))
    recording = Recording(
        tenant_id=tenant.id, camera_id=camera_id, file_path="/tmp/does-not-exist.mp4",
        started_at=datetime.now(timezone.utc), trigger_type=RecordingTrigger.MANUAL,
    )
    db_session.add_all([detection, snapshot, recording])
    db_session.commit()

    # Cross-reference them exactly like the real pipeline does (app/api/routes/events.py,
    # ai-engine/app/worker.py) — this is what makes the circular FK relationship real.
    detection.snapshot_id, detection.recording_id = snapshot.id, recording.id
    db_session.commit()

    event = Event(
        tenant_id=tenant.id, camera_id=camera_id, event_type=EventType.PERSON_DETECTED,
        severity=EventSeverity.INFO, detection_id=detection.id, snapshot_id=snapshot.id,
        recording_id=recording.id, occurred_at=datetime.now(timezone.utc), event_metadata={},
    )
    db_session.add(event)
    db_session.commit()

    rule = AIRule(tenant_id=tenant.id, name="Camera-scoped rule", camera_id=camera_id, conditions={"event_type": "PERSON_DETECTED"})
    db_session.add(rule)
    db_session.commit()

    alert = Alert(tenant_id=tenant.id, event_id=event.id, camera_id=camera_id, rule_id=rule.id, alert_type="TEST", severity=EventSeverity.HIGH)
    zone = Zone(tenant_id=tenant.id, camera_id=camera_id, name="Zone", zone_type=ZoneType.INTRUSION, polygon=[[0, 0], [1, 0], [1, 1]])
    tripwire = Tripwire(tenant_id=tenant.id, camera_id=camera_id, name="Line", line=[[0, 0], [1, 1]])

    person = Person(tenant_id=tenant.id, first_name="Jane", last_name="Doe", category=PersonCategory.EMPLOYEE)
    db_session.add(person)
    db_session.commit()
    face_profile = FaceProfile(tenant_id=tenant.id, person_id=person.id, embedding_encrypted="x", model_version="lbph-v1")
    db_session.add(face_profile)
    db_session.commit()
    face_event = FaceRecognitionEvent(
        tenant_id=tenant.id, event_id=event.id, camera_id=camera_id, person_id=person.id,
        face_profile_id=face_profile.id, recognition_status=RecognitionStatus.RECOGNIZED,
        event_timestamp=datetime.now(timezone.utc),
    )

    db_session.add_all([alert, zone, tripwire, face_event])
    db_session.commit()
    rule_id = rule.id

    resp = client.delete(f"/api/cameras/{camera_id}", headers=auth_headers(token))
    assert resp.status_code == 204, resp.text

    # The route ran against a different Session instance (app's get_db override) than
    # db_session here — both share the same underlying SQLite connection (StaticPool),
    # but db_session's identity map still holds the pre-delete Python objects unless
    # told to refetch.
    db_session.expire_all()

    assert client.get(f"/api/cameras/{camera_id}", headers=auth_headers(token)).status_code == 404
    assert db_session.query(Detection).filter(Detection.camera_id == camera_id).count() == 0
    assert db_session.query(Snapshot).filter(Snapshot.camera_id == camera_id).count() == 0
    assert db_session.query(Recording).filter(Recording.camera_id == camera_id).count() == 0
    assert db_session.query(Event).filter(Event.camera_id == camera_id).count() == 0
    assert db_session.query(Alert).filter(Alert.camera_id == camera_id).count() == 0
    assert db_session.query(Zone).filter(Zone.camera_id == camera_id).count() == 0
    assert db_session.query(Tripwire).filter(Tripwire.camera_id == camera_id).count() == 0
    assert db_session.query(FaceRecognitionEvent).filter(FaceRecognitionEvent.camera_id == camera_id).count() == 0

    # The rule itself survives, just unscoped — deleting a camera must not silently
    # delete an administrator's configured rule as a side effect.
    surviving_rule = db_session.get(AIRule, rule_id)
    assert surviving_rule is not None
    assert surviving_rule.camera_id is None

    # The enrolled person (not camera-specific data) is untouched.
    assert db_session.get(Person, person.id) is not None


def test_delete_camera_still_works_with_no_dependent_data(client, admin_user):
    """Regression guard: the simple case (from test_cameras.py) must keep working."""
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Empty Cam", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.delete(f"/api/cameras/{cam['id']}", headers=auth_headers(token))
    assert resp.status_code == 204
