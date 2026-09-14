"""AI Video Intelligence Phase 1: gate-jumping/climbing heuristic (spec section 4) and
tailgating detection (section 8) for tripwire crossings.

Both are real, transparent, and honestly approximate — see each function/class's own
docstring for exactly what signal it uses and what it does NOT verify. Neither is a
trained classifier; there is no such model in this environment (see CLAUDE.md "Known
limitations"). Constants below were originally tuned against synthetic test
trajectories only — GATE_JUMP_MIN_VERTICAL_STEP has since been adjusted once against
real footage (see its own comment), the first time this has actually happened.
"""

# ~1.5s of history at the default 5 ai_fps (CentroidTracker keeps up to 50 samples).
GATE_JUMP_WINDOW = 8
# Minimum peak per-sample vertical displacement (normalized 0-1 frame-height units) to
# even consider a crossing anomalous — below this, it's ordinary frame-to-frame noise.
# Real footage found live: a genuine gate jump measured peak_vertical=0.114 (twice),
# just under the original 0.12 — and with a short (7-of-8-sample) window, suggesting
# CentroidTracker's own max_distance briefly lost the track right at the jump's peak
# displacement, truncating the very history this heuristic reads. Lowered to 0.10,
# comfortably below the two real 0.114 measurements and still far above the ordinary
# walk-noise this same camera logged (0.024) — see worker.py's diagnostic logging
# (added alongside this fix) for how these real numbers were captured in the first
# place, instead of guessing at a new value blindly.
GATE_JUMP_MIN_VERTICAL_STEP = 0.10
# The peak vertical step must also clearly dominate the track's own recent horizontal
# pace — this is what tells a genuine climb/jump (mostly-vertical motion) apart from a
# fast diagonal walk (proportionally similar vertical and horizontal motion).
GATE_JUMP_VELOCITY_RATIO = 2.0


def gate_jump_trajectory_stats(history: list[tuple[float, float]]) -> tuple[float, float, int] | None:
    """The raw numbers gate_jump_confidence's decision is based on — split out so a
    caller (worker.py logs these at the point of every crossing when the heuristic
    does NOT fire) can see exactly why a real crossing wasn't classified as a jump,
    instead of only ever seeing a silent None. Real need: this heuristic was tuned
    against synthetic trajectories only (see module docstring) — tuning
    GATE_JUMP_MIN_VERTICAL_STEP/GATE_JUMP_VELOCITY_RATIO against real footage requires
    seeing what real crossings actually measure as, not guessing blindly.
    Returns (peak_vertical, avg_horizontal, window_length), or None if there isn't
    enough history yet to compute anything."""
    window = history[-GATE_JUMP_WINDOW:]
    if len(window) < 3:
        return None

    vertical_steps = [abs(window[i][1] - window[i - 1][1]) for i in range(1, len(window))]
    horizontal_steps = [abs(window[i][0] - window[i - 1][0]) for i in range(1, len(window))]

    peak_vertical = max(vertical_steps)
    avg_horizontal = sum(horizontal_steps) / len(horizontal_steps)
    return peak_vertical, avg_horizontal, len(window)


def gate_jump_confidence(history: list[tuple[float, float]]) -> float | None:
    """`history` is a track's recent (x, y) centroid samples, oldest first (see
    CentroidTracker.history_for) — normalized 0-1 coordinates. Returns a confidence in
    [0.5, 0.99] if the track's recent trajectory looks like a climb/jump rather than an
    ordinary walk-through, else None (treat as a normal crossing, matching the
    platform's existing behavior before this feature existed).
    """
    stats = gate_jump_trajectory_stats(history)
    if stats is None:
        return None
    peak_vertical, avg_horizontal, _ = stats

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
