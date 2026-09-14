"""AI Video Intelligence Phase 2: 'potential theft / unauthorized object removal'
(section 6) — a real, transparent dwell-then-exit heuristic, not a trained
theft/behavior classifier. See CLAUDE.md 'Known limitations' for exactly what this
does and does not detect.
"""

import logging

logger = logging.getLogger("ai-engine.object_tracking")


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
        # Real, honest instrumentation — this heuristic has never been exercised
        # against a real object before, and worker.py has no success/failure log of
        # its own for the event it creates (see backend_client.py — only failed POSTs
        # are logged). Without this, "why didn't a real bag removal get flagged"
        # would be as undebuggable from the outside as the face-recognition quality
        # gate was before it got the same treatment.
        key = (track_id, zone_id)
        if inside:
            if key not in self._entered_at:
                logger.info("Zone %s: track %s entered the asset zone — dwell timer started", zone_id, track_id)
            self._entered_at.setdefault(key, now)
            return False

        entered_at = self._entered_at.pop(key, None)
        if entered_at is None:
            return False
        dwell = now - entered_at
        fired = dwell >= threshold_seconds
        logger.info(
            "Zone %s: track %s left the asset zone after %.1fs (threshold %ds) — %s",
            zone_id, track_id, dwell, threshold_seconds,
            "flagging as POTENTIAL_THEFT_DETECTED" if fired else "not flagged, dwell was too short",
        )
        return fired
