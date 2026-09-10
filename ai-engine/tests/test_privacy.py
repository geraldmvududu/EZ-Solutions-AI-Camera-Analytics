import numpy as np

from app.core.privacy import apply_privacy_masks


def _solid_frame(color: int = 200) -> np.ndarray:
    return np.full((200, 200, 3), color, dtype=np.uint8)


def test_no_zones_returns_frame_unchanged():
    frame = _solid_frame()
    result = apply_privacy_masks(frame, [])
    assert np.array_equal(result, frame)


def test_privacy_zone_blurs_only_masked_region():
    frame = _solid_frame(0)
    # Put a sharp bright square entirely inside the privacy zone region.
    frame[80:120, 80:120] = 255

    zone = {"polygon": [[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]], "zone_type": "PRIVACY"}
    result = apply_privacy_masks(frame, [zone])

    # Inside the masked region, the sharp edge should be smeared (blurred), so the
    # exact corner pixel should no longer be pure white/black — it changed.
    assert not np.array_equal(result[80:120, 80:120], frame[80:120, 80:120])

    # Outside the zone, pixels are completely untouched.
    assert np.array_equal(result[0:10, 0:10], frame[0:10, 0:10])


def test_degenerate_polygon_is_ignored():
    frame = _solid_frame()
    zone = {"polygon": [[0.1, 0.1], [0.2, 0.2]], "zone_type": "PRIVACY"}  # only 2 points
    result = apply_privacy_masks(frame, [zone])
    assert np.array_equal(result, frame)
