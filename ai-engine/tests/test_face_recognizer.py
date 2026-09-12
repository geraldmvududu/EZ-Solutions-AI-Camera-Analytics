"""FaceRecognizer (spec sections 4/19): cooldown, zone filtering, operating hours,
and — critically — that a failure anywhere in this pipeline never raises out of
maybe_recognize (a recognition bug must never stop the camera's capture/recording
loop)."""

from datetime import time as dt_time

import numpy as np

from app.core import face_embedding, face_recognizer as fr_module
from app.core.face_recognizer import IDENTITY_FRESHNESS_SECONDS, FaceRecognizer, _within_operating_hours
from app.detectors.base import Detection


def _person_detection() -> Detection:
    return Detection(object_type="PERSON", confidence=0.9, x=0.1, y=0.1, width=0.3, height=0.5)


def _frame() -> np.ndarray:
    return np.full((400, 400, 3), 128, dtype=np.uint8)


def test_within_operating_hours_simple_window():
    camera = {"face_operating_hours_start": "06:00", "face_operating_hours_end": "22:00"}
    assert _within_operating_hours(camera, now=dt_time(12, 0)) is True
    assert _within_operating_hours(camera, now=dt_time(23, 0)) is False


def test_within_operating_hours_wraps_midnight():
    camera = {"face_operating_hours_start": "22:00", "face_operating_hours_end": "05:00"}
    assert _within_operating_hours(camera, now=dt_time(23, 30)) is True
    assert _within_operating_hours(camera, now=dt_time(12, 0)) is False


def test_within_operating_hours_unset_means_always_active():
    assert _within_operating_hours({}, now=dt_time(3, 0)) is True


def test_cooldown_prevents_immediate_re_recognition(monkeypatch):
    monkeypatch.setattr(face_embedding, "assess_recognition_quality", lambda crop, q: face_embedding.QualityCheckResult(
        True, "", 1, face_embedding.DetectedFace(0, 0, 50, 50), 0.9, 0.9, 0.9, 0.9
    ))
    monkeypatch.setattr(face_embedding, "compute_embedding", lambda crop, face: np.zeros(10, dtype=np.float32))
    monkeypatch.setattr(fr_module, "save_snapshot", lambda camera_id, frame: "/tmp/fake.jpg")

    calls = []
    monkeypatch.setattr(fr_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: calls.append(payload) or {"recognition_status": "UNKNOWN", "confidence_score": 0.0})

    recognizer = FaceRecognizer("cam-1")
    camera = {"face_recognition_enabled": True}
    detection = _person_detection()
    centroid = (0.25, 0.35)

    recognizer.maybe_recognize(camera, _frame(), 1, detection, centroid, [])
    recognizer.maybe_recognize(camera, _frame(), 1, detection, centroid, [])  # immediate retry, same track

    assert len(calls) == 1


def test_cooldown_uses_camera_dict_value_over_static_setting(monkeypatch):
    """recognition_cooldown_seconds is a tenant-level FaceRecognitionSettings field
    flattened onto the camera dict by GET /cameras/internal/active (same as
    liveness_detection_enabled) — an admin's Settings change must actually change
    behavior here, not just sit unused while ai-engine keeps using its own static
    FACE_EVENT_COOLDOWN env var."""
    monkeypatch.setattr(face_embedding, "assess_recognition_quality", lambda crop, q: face_embedding.QualityCheckResult(
        True, "", 1, face_embedding.DetectedFace(0, 0, 50, 50), 0.9, 0.9, 0.9, 0.9
    ))
    monkeypatch.setattr(face_embedding, "compute_embedding", lambda crop, face: np.zeros(10, dtype=np.float32))
    monkeypatch.setattr(fr_module, "save_snapshot", lambda camera_id, frame: "/tmp/fake.jpg")
    monkeypatch.setattr(fr_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})

    calls = []
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: calls.append(payload) or {"recognition_status": "UNKNOWN", "confidence_score": 0.0})

    recognizer = FaceRecognizer("cam-1")
    # The static settings.face_event_cooldown default (30s, see app/config.py) would
    # normally block a second immediate attempt — an explicit 0-second cooldown on the
    # camera dict must override that and let the second attempt through.
    camera = {"face_recognition_enabled": True, "recognition_cooldown_seconds": 0}
    detection = _person_detection()
    centroid = (0.25, 0.35)

    recognizer.maybe_recognize(camera, _frame(), 1, detection, centroid, [])
    recognizer.maybe_recognize(camera, _frame(), 1, detection, centroid, [])  # immediate retry, same track

    assert len(calls) == 2


def test_face_exclusion_zone_blocks_recognition(monkeypatch):
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: (_ for _ in ()).throw(AssertionError("should not be called")))
    recognizer = FaceRecognizer("cam-1")
    camera = {"face_recognition_enabled": True}
    exclusion_zone = {"zone_type": "FACE_EXCLUSION", "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]}

    # Should return cleanly (no exception) despite the assertion-raising mock, because
    # the exclusion-zone check must short-circuit before ever calling recognize_face.
    recognizer.maybe_recognize(camera, _frame(), 1, _person_detection(), (0.5, 0.5), [exclusion_zone])


def test_face_detection_zone_allowlist_blocks_outside_points(monkeypatch):
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: (_ for _ in ()).throw(AssertionError("should not be called")))
    recognizer = FaceRecognizer("cam-1")
    camera = {"face_recognition_enabled": True}
    detection_zone = {"zone_type": "FACE_DETECTION", "polygon": [[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]]}

    # Centroid (0.5, 0.5) is outside the only FACE_DETECTION zone -> must be skipped.
    recognizer.maybe_recognize(camera, _frame(), 1, _person_detection(), (0.5, 0.5), [detection_zone])


def test_exception_in_pipeline_never_propagates(monkeypatch):
    def boom(crop, q):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(face_embedding, "assess_recognition_quality", boom)
    recognizer = FaceRecognizer("cam-1")
    camera = {"face_recognition_enabled": True}

    # Must not raise — a recognition bug can never take down the capture loop.
    recognizer.maybe_recognize(camera, _frame(), 1, _person_detection(), (0.25, 0.35), [])


def _mock_quality_and_embedding(monkeypatch):
    monkeypatch.setattr(face_embedding, "assess_recognition_quality", lambda crop, q: face_embedding.QualityCheckResult(
        True, "", 1, face_embedding.DetectedFace(0, 0, 50, 50), 0.9, 0.9, 0.9, 0.9
    ))
    monkeypatch.setattr(face_embedding, "compute_embedding", lambda crop, face: np.zeros(10, dtype=np.float32))
    monkeypatch.setattr(fr_module, "save_snapshot", lambda camera_id, frame: "/tmp/fake.jpg")
    monkeypatch.setattr(fr_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})


def test_recording_id_is_forwarded_to_recognize_payload(monkeypatch):
    _mock_quality_and_embedding(monkeypatch)
    calls = []
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: calls.append(payload) or {"recognition_status": "UNKNOWN"})

    recognizer = FaceRecognizer("cam-1")
    recognizer.maybe_recognize({"face_recognition_enabled": True}, _frame(), 1, _person_detection(), (0.25, 0.35), [], "rec-abc")

    assert calls[0]["recording_id"] == "rec-abc"


def test_liveness_first_attempt_passes_with_nothing_to_compare(monkeypatch):
    _mock_quality_and_embedding(monkeypatch)
    calls = []
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: calls.append(payload) or {"recognition_status": "UNKNOWN"})

    recognizer = FaceRecognizer("cam-1")
    recognizer.maybe_recognize({"face_recognition_enabled": True, "liveness_detection_enabled": True}, _frame(), 1, _person_detection(), (0.25, 0.35), [])

    assert len(calls) == 1  # nothing to compare against yet — fails open


def test_liveness_rejects_a_perfectly_static_repeated_crop(monkeypatch):
    _mock_quality_and_embedding(monkeypatch)
    calls = []
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: calls.append(payload) or {"recognition_status": "UNKNOWN"})

    recognizer = FaceRecognizer("cam-1")
    camera = {"face_recognition_enabled": True, "liveness_detection_enabled": True}
    # Bypass the cooldown by manipulating internal state directly rather than sleeping.
    recognizer._last_attempt[1] = 0.0

    identical_frame = _frame()
    recognizer.maybe_recognize(camera, identical_frame, 1, _person_detection(), (0.25, 0.35), [])
    recognizer._last_attempt[1] = 0.0  # simulate the cooldown having elapsed
    recognizer.maybe_recognize(camera, identical_frame, 1, _person_detection(), (0.25, 0.35), [])

    # First attempt has nothing to compare against (passes); second is pixel-identical
    # to the first (a real live camera would never produce two byte-identical frames)
    # and must be rejected before ever calling recognize_face.
    assert len(calls) == 1


def test_liveness_accepts_a_genuinely_different_crop(monkeypatch):
    _mock_quality_and_embedding(monkeypatch)
    calls = []
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: calls.append(payload) or {"recognition_status": "UNKNOWN"})

    recognizer = FaceRecognizer("cam-1")
    camera = {"face_recognition_enabled": True, "liveness_detection_enabled": True}

    frame_a = _frame()
    frame_b = np.full((400, 400, 3), 200, dtype=np.uint8)  # clearly different brightness

    recognizer._last_attempt[1] = 0.0
    recognizer.maybe_recognize(camera, frame_a, 1, _person_detection(), (0.25, 0.35), [])
    recognizer._last_attempt[1] = 0.0
    recognizer.maybe_recognize(camera, frame_b, 1, _person_detection(), (0.25, 0.35), [])

    assert len(calls) == 2


def test_liveness_disabled_by_default_ignores_static_repeats(monkeypatch):
    """Regression guard: liveness_detection_enabled defaults to falsy/absent — a
    camera dict without it must behave exactly as before this feature existed."""
    _mock_quality_and_embedding(monkeypatch)
    calls = []
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: calls.append(payload) or {"recognition_status": "UNKNOWN"})

    recognizer = FaceRecognizer("cam-1")
    camera = {"face_recognition_enabled": True}
    identical_frame = _frame()

    recognizer._last_attempt[1] = 0.0
    recognizer.maybe_recognize(camera, identical_frame, 1, _person_detection(), (0.25, 0.35), [])
    recognizer._last_attempt[1] = 0.0
    recognizer.maybe_recognize(camera, identical_frame, 1, _person_detection(), (0.25, 0.35), [])

    assert len(calls) == 2


def test_low_quality_face_skips_without_calling_backend(monkeypatch):
    monkeypatch.setattr(face_embedding, "assess_recognition_quality", lambda crop, q: face_embedding.QualityCheckResult(
        False, "too small", 0, None, 0.0, 0.0, 0.0, 0.0
    ))
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: (_ for _ in ()).throw(AssertionError("should not be called")))

    recognizer = FaceRecognizer("cam-1")
    recognizer.maybe_recognize({"face_recognition_enabled": True}, _frame(), 1, _person_detection(), (0.25, 0.35), [])


def _mock_recognition_pipeline(monkeypatch, recognize_result: dict):
    monkeypatch.setattr(face_embedding, "assess_recognition_quality", lambda crop, q: face_embedding.QualityCheckResult(
        True, "", 1, face_embedding.DetectedFace(0, 0, 50, 50), 0.9, 0.9, 0.9, 0.9
    ))
    monkeypatch.setattr(face_embedding, "compute_embedding", lambda crop, face: np.zeros(10, dtype=np.float32))
    monkeypatch.setattr(fr_module, "save_snapshot", lambda camera_id, frame: "/tmp/fake.jpg")
    monkeypatch.setattr(fr_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})
    monkeypatch.setattr(fr_module.backend_client, "recognize_face", lambda payload: recognize_result)


def test_identity_for_returns_none_when_never_recognized():
    recognizer = FaceRecognizer("cam-1")
    assert recognizer.identity_for(42) is None


def test_identity_for_tracks_a_recognized_result(monkeypatch):
    _mock_recognition_pipeline(monkeypatch, {"recognition_status": "RECOGNIZED", "person_id": "person-123", "person_name": "Jane Doe", "confidence_score": 0.94})

    recognizer = FaceRecognizer("cam-1")
    recognizer.maybe_recognize({"face_recognition_enabled": True}, _frame(), 7, _person_detection(), (0.25, 0.35), [])

    identity = recognizer.identity_for(7)
    assert identity == {"person_id": "person-123", "person_name": "Jane Doe", "confidence_score": 0.94}


def test_identity_for_does_not_track_unknown_results(monkeypatch):
    _mock_recognition_pipeline(monkeypatch, {"recognition_status": "UNKNOWN", "person_id": None, "person_name": None, "confidence_score": 0.0})

    recognizer = FaceRecognizer("cam-1")
    recognizer.maybe_recognize({"face_recognition_enabled": True}, _frame(), 7, _person_detection(), (0.25, 0.35), [])

    assert recognizer.identity_for(7) is None


def test_identity_for_expires_after_freshness_window(monkeypatch):
    _mock_recognition_pipeline(monkeypatch, {"recognition_status": "RECOGNIZED", "person_id": "person-123", "person_name": "Jane Doe", "confidence_score": 0.94})

    recognizer = FaceRecognizer("cam-1")
    recognizer.maybe_recognize({"face_recognition_enabled": True}, _frame(), 7, _person_detection(), (0.25, 0.35), [])
    assert recognizer.identity_for(7) is not None

    # Age the stored entry past the freshness window directly, rather than
    # monkeypatching time.time() globally (which would also affect the cooldown check).
    seen_at, identity = recognizer._known_identities[7]
    recognizer._known_identities[7] = (seen_at - IDENTITY_FRESHNESS_SECONDS - 1, identity)

    assert recognizer.identity_for(7) is None
