from app.core.object_tracking import AssetZoneTracker


def test_exit_before_threshold_does_not_fire():
    tracker = AssetZoneTracker()
    tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=10, now=0.0)
    fired = tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=5.0)
    assert fired is False


def test_exit_after_threshold_fires_once():
    tracker = AssetZoneTracker()
    tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=10, now=0.0)
    fired = tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=15.0)
    assert fired is True

    # The same continuous "not inside" state must not re-fire on the next frame.
    fired_again = tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=16.0)
    assert fired_again is False


def test_never_entered_zone_does_not_fire_on_exit_check():
    tracker = AssetZoneTracker()
    fired = tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=0.0)
    assert fired is False


def test_reentry_after_a_fired_exit_can_fire_again():
    tracker = AssetZoneTracker()
    tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=10, now=0.0)
    assert tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=15.0) is True

    # Object is placed back, dwells long enough again, then removed a second time.
    tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=10, now=20.0)
    assert tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=35.0) is True


def test_a_too_short_dwell_does_not_fire_and_does_not_leak_into_a_later_check():
    tracker = AssetZoneTracker()
    tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=10, now=0.0)
    # Only dwelled 3s before leaving — must not fire.
    assert tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=3.0) is False

    # A fresh, also-too-short dwell later must not fire either, and continuing to be
    # observed outside afterwards (no new entry) must never fire just from elapsed
    # wall-clock time.
    tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=10, now=20.0)
    assert tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=25.0) is False
    assert tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=10, now=100.0) is False


def test_different_zones_are_tracked_independently():
    tracker = AssetZoneTracker()
    tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=10, now=0.0)
    fired_other_zone = tracker.observe(track_id=1, zone_id="z2", inside=False, threshold_seconds=10, now=15.0)
    assert fired_other_zone is False
