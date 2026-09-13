from app.core.tracker import CentroidTracker
from app.detectors.base import Detection


def _det(x: float, y: float, object_type: str = "PERSON") -> Detection:
    return Detection(object_type=object_type, confidence=0.9, x=x, y=y, width=0.1, height=0.2)


def test_new_detection_gets_new_track_id():
    tracker = CentroidTracker()
    tracked = tracker.update([_det(0.1, 0.1)])
    assert list(tracked.keys()) == [1]


def test_same_object_keeps_same_track_id_across_frames():
    tracker = CentroidTracker()
    tracker.update([_det(0.10, 0.10)])
    tracked = tracker.update([_det(0.11, 0.11)])  # small movement, same person
    assert list(tracked.keys()) == [1]


def test_far_away_detection_gets_new_track_id():
    tracker = CentroidTracker(max_distance=0.15)
    tracker.update([_det(0.1, 0.1)])
    tracked = tracker.update([_det(0.9, 0.9)])  # far away -> different person
    assert list(tracked.keys()) == [2]


def test_track_evicted_after_max_disappeared_frames():
    tracker = CentroidTracker(max_disappeared=2)
    tracker.update([_det(0.1, 0.1)])
    tracker.update([])  # disappeared frame 1
    tracker.update([])  # disappeared frame 2
    tracker.update([])  # disappeared frame 3 -> evicted
    tracked = tracker.update([_det(0.1, 0.1)])
    assert list(tracked.keys()) == [2]  # new id, not reused


def test_person_and_backpack_at_the_same_position_stay_on_separate_tracks():
    # Real gap a multi-class detector (YoloDetector) exposes that HOG never could:
    # a person carrying a backpack produces two detections at nearly the same
    # centroid every frame. Nearest-centroid-only matching would let one steal the
    # other's track, corrupting object_type mid-track.
    tracker = CentroidTracker()
    tracked = tracker.update([_det(0.50, 0.50, "PERSON"), _det(0.51, 0.51, "BACKPACK")])
    assert set(tracked.keys()) == {1, 2}
    assert tracked[1].object_type == "PERSON"
    assert tracked[2].object_type == "BACKPACK"

    tracked = tracker.update([_det(0.52, 0.52, "PERSON"), _det(0.53, 0.53, "BACKPACK")])
    assert set(tracked.keys()) == {1, 2}
    assert tracked[1].object_type == "PERSON"
    assert tracked[2].object_type == "BACKPACK"


def test_history_for_tracks_centroid_path():
    tracker = CentroidTracker()
    tracker.update([_det(0.1, 0.1)])
    tracker.update([_det(0.2, 0.2)])
    history = tracker.history_for(1)
    assert len(history) == 2
    assert history[0] != history[1]
