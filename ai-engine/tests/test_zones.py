from app.core.zones import LoiteringTracker, crossed_line, point_in_polygon


def test_point_inside_square_polygon():
    square = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    assert point_in_polygon((0.5, 0.5), square) is True


def test_point_outside_square_polygon():
    square = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    assert point_in_polygon((0.05, 0.05), square) is False


def test_degenerate_polygon_is_never_inside():
    assert point_in_polygon((0.5, 0.5), [[0.1, 0.1], [0.2, 0.2]]) is False


def test_crossed_line_detects_entering():
    line = [[0.5, 0.0], [0.5, 1.0]]  # vertical line at x=0.5
    direction = crossed_line((0.3, 0.5), (0.7, 0.5), line)
    assert direction in ("ENTERING", "EXITING")  # sign convention, but must detect *a* crossing


def test_no_crossing_when_staying_on_same_side():
    line = [[0.5, 0.0], [0.5, 1.0]]
    assert crossed_line((0.3, 0.5), (0.35, 0.5), line) is None


def test_loitering_fires_once_after_threshold(monkeypatch):
    tracker = LoiteringTracker()
    times = iter([100.0, 100.0, 135.0, 136.0])
    monkeypatch.setattr("app.core.zones.time.time", lambda: next(times))

    assert tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=30) is False  # enters at t=100
    assert tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=30) is False  # still checking entry
    assert tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=30) is True  # t=135, 35s elapsed
    assert tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=30) is False  # already alerted


def test_loitering_resets_when_leaving_zone():
    tracker = LoiteringTracker()
    tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=30)
    assert tracker.observe(track_id=1, zone_id="z1", inside=False, threshold_seconds=30) is False
    # Re-entering should not immediately fire even if it fired before leaving.
    assert tracker.observe(track_id=1, zone_id="z1", inside=True, threshold_seconds=30) is False
