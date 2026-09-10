"""Real geometry for intrusion/privacy zones, virtual tripwires, and loitering timers
(sections 20-22). All inputs/outputs are normalized 0-1 frame coordinates, matching how
zones/tripwires are stored via the backend API."""

import time

Point = tuple[float, float]


def point_in_polygon(point: Point, polygon: list[list[float]]) -> bool:
    """Standard ray-casting point-in-polygon test."""
    x, y = point
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _side_of_line(point: Point, line: list[list[float]]) -> float:
    (x1, y1), (x2, y2) = line
    x, y = point
    return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)


def crossed_line(prev_point: Point, current_point: Point, line: list[list[float]]) -> str | None:
    """Returns 'ENTERING', 'EXITING', or None depending on which side of the tripwire
    line the point moved from/to. The ENTERING/EXITING label is a convention (positive
    side -> negative side = ENTERING) — direction filtering in the tripwire config
    decides whether that specific crossing should raise an event."""
    prev_side = _side_of_line(prev_point, line)
    curr_side = _side_of_line(current_point, line)
    if prev_side == 0 or curr_side == 0 or (prev_side > 0) == (curr_side > 0):
        return None
    return "ENTERING" if prev_side > 0 > curr_side else "EXITING"


class LoiteringTracker:
    """Tracks how long each (track_id, zone_id) pair has continuously been observed
    inside a zone, and reports when it first crosses the configured threshold (fires
    once per continuous stay, not once per frame)."""

    def __init__(self) -> None:
        self._entered_at: dict[tuple[int, str], float] = {}
        self._alerted: set[tuple[int, str]] = set()

    def observe(self, track_id: int, zone_id: str, inside: bool, threshold_seconds: int) -> bool:
        key = (track_id, zone_id)
        if not inside:
            self._entered_at.pop(key, None)
            self._alerted.discard(key)
            return False

        now = time.time()
        entered_at = self._entered_at.setdefault(key, now)
        duration = now - entered_at

        if duration >= threshold_seconds and key not in self._alerted:
            self._alerted.add(key)
            return True
        return False
