"""AI Video Intelligence Phase 1: gate-jumping/climbing heuristic (spec section 4) and
tailgating detection (section 8) for tripwire crossings.

Both are real, transparent, and honestly approximate — see each function/class's own
docstring for exactly what signal it uses and what it does NOT verify. Neither is a
trained classifier; there is no such model in this environment (see CLAUDE.md "Known
limitations"). Constants below were tuned against synthetic test trajectories only
(tests/test_gate_jumping.py) — validate against real footage once deployed.
"""

# ~1.5s of history at the default 5 ai_fps (CentroidTracker keeps up to 50 samples).
GATE_JUMP_WINDOW = 8
# Minimum peak per-sample vertical displacement (normalized 0-1 frame-height units) to
# even consider a crossing anomalous — below this, it's ordinary frame-to-frame noise.
GATE_JUMP_MIN_VERTICAL_STEP = 0.12
# The peak vertical step must also clearly dominate the track's own recent horizontal
# pace — this is what tells a genuine climb/jump (mostly-vertical motion) apart from a
# fast diagonal walk (proportionally similar vertical and horizontal motion).
GATE_JUMP_VELOCITY_RATIO = 2.0


def gate_jump_confidence(history: list[tuple[float, float]]) -> float | None:
    """`history` is a track's recent (x, y) centroid samples, oldest first (see
    CentroidTracker.history_for) — normalized 0-1 coordinates. Returns a confidence in
    [0.5, 0.99] if the track's recent trajectory looks like a climb/jump rather than an
    ordinary walk-through, else None (treat as a normal crossing, matching the
    platform's existing behavior before this feature existed).
    """
    window = history[-GATE_JUMP_WINDOW:]
    if len(window) < 3:
        return None

    vertical_steps = [abs(window[i][1] - window[i - 1][1]) for i in range(1, len(window))]
    horizontal_steps = [abs(window[i][0] - window[i - 1][0]) for i in range(1, len(window))]

    peak_vertical = max(vertical_steps)
    avg_horizontal = sum(horizontal_steps) / len(horizontal_steps)

    if peak_vertical < GATE_JUMP_MIN_VERTICAL_STEP:
        return None
    if avg_horizontal > 0 and peak_vertical < GATE_JUMP_VELOCITY_RATIO * avg_horizontal:
        return None

    excess = (peak_vertical - GATE_JUMP_MIN_VERTICAL_STEP) / GATE_JUMP_MIN_VERTICAL_STEP
    return max(0.5, min(0.99, 0.5 + excess * 0.25))


class TailgatingTracker:
    """Real time-window multi-crossing detection per tripwire (spec section 8): if a
    second, DIFFERENT track crosses the same tripwire within its configured window of a
    prior crossing, the later crossing is flagged as tailgating. This platform has no
    access-control-system integration (see CLAUDE.md "Known limitations"), so
    "authorized access event" here just means "the first crossing observed in the
    window" — a real door/gate/turnstile access-control correlation would be a
    materially stronger signal than tripwire-only video analysis.
    """

    def __init__(self) -> None:
        self._last_crossing: dict[str, tuple[int, float]] = {}

    def observe(self, tripwire_id: str, track_id: int, now: float, window_seconds: int) -> int | None:
        """Records this crossing and returns the earlier track_id being tailgated if
        this one is a tailgating event, else None. Always updates state regardless of
        outcome, so each tripwire only ever remembers its single most recent crossing."""
        prior = self._last_crossing.get(tripwire_id)
        self._last_crossing[tripwire_id] = (track_id, now)
        if prior is None:
            return None
        prior_track_id, prior_time = prior
        if prior_track_id == track_id:
            return None
        if now - prior_time > window_seconds:
            return None
        return prior_track_id
