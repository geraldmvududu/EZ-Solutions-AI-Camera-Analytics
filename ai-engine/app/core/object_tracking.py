"""AI Video Intelligence Phase 2: 'potential theft / unauthorized object removal'
(section 6) — a real, transparent dwell-then-exit heuristic, not a trained
theft/behavior classifier. See CLAUDE.md 'Known limitations' for exactly what this
does and does not detect.
"""


class AssetZoneTracker:
    """Tracks how long each (track_id, zone_id) pair has continuously been observed
    inside an ASSET_ZONE, and reports the first frame that track is observed OUTSIDE
    the zone again, provided it had been inside for at least threshold_seconds first.
    Structurally similar to zones.py::LoiteringTracker, but with inverted trigger
    semantics: LoiteringTracker fires on continued presence, this fires on exit.

    Takes an explicit `now` parameter (matching TailgatingTracker.observe's
    convention) rather than calling time.time() internally, for testability.

    Real, honest limitation: this only fires while the object remains independently
    classifiable by the detector as it crosses the zone boundary. An object that
    becomes occluded before then — hidden under clothing, placed inside another bag,
    put in a vehicle trunk — will not be caught, since at that point the detector can
    no longer see it as a distinct BACKPACK/BAG/SUITCASE to track.
    """

    def __init__(self) -> None:
        self._entered_at: dict[tuple[int, str], float] = {}

    def observe(self, track_id: int, zone_id: str, inside: bool, threshold_seconds: int, now: float) -> bool:
        key = (track_id, zone_id)
        if inside:
            self._entered_at.setdefault(key, now)
            return False

        entered_at = self._entered_at.pop(key, None)
        if entered_at is None:
            return False
        return (now - entered_at) >= threshold_seconds
