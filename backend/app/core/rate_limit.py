"""Redis-backed rate limiting (section 46), replacing the earlier per-process
in-memory limiter — that version's counters lived in one Python process's memory, so
running more than one backend replica (Phase 9 / multi-VM) let a client get
`MAX_REQUESTS` per replica instead of per deployment. A shared Redis counter fixes
that: every replica increments the same key.

Uses a simple fixed-window counter (INCR + EXPIRE) rather than a sliding-window log —
atomic enough for abuse protection, and far cheaper than a sorted-set sliding window.
Its one known imprecision: a client can burst up to ~2x the limit across a window
boundary. Acceptable for this platform's threat model (abuse/DoS protection, not
precise quota enforcement).
"""

import logging
import time

import redis

from app.config import get_settings

logger = logging.getLogger("app.rate_limit")
settings = get_settings()

WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 300

# Once Redis fails, skip it entirely for this long before probing it again. Without
# this, every single request pays a full connect-timeout penalty (measured ~2s on
# Windows when nothing is listening on the port) for as long as Redis stays down —
# turning "fail open to a fallback" into "every request hangs for 2 seconds". This was
# caught by measuring real request latency against a live server with no Redis
# running, not by unit tests (fakeredis never exercises the actual timeout path).
REDIS_DOWN_COOLDOWN_SECONDS = 10

_redis_client: redis.Redis | None = None
_redis_down_until: float = 0.0

# Fallback used only when Redis itself is unreachable, so a single-instance/local-dev
# deployment still gets *some* protection instead of the limiter silently doing
# nothing. Not shared across processes/replicas — that's the whole reason Redis exists.
_fallback_counts: dict[str, tuple[int, int]] = {}  # ip -> (window_index, count)


def _get_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
    return _redis_client


def _fallback_is_limited(client_ip: str) -> bool:
    window_index = int(time.time() // WINDOW_SECONDS)
    stored_window, count = _fallback_counts.get(client_ip, (window_index, 0))
    if stored_window != window_index:
        count = 0
    count += 1
    _fallback_counts[client_ip] = (window_index, count)
    return count > MAX_REQUESTS_PER_WINDOW


def is_rate_limited(client_ip: str) -> bool:
    """Returns True if `client_ip` has exceeded MAX_REQUESTS_PER_WINDOW in the current
    fixed window. Fails open to the in-memory fallback (never blocks all traffic) if
    Redis is unreachable, and — once it has failed once — stops paying the connection-
    timeout cost on every request until REDIS_DOWN_COOLDOWN_SECONDS have passed."""
    global _redis_down_until

    now = time.time()
    if now < _redis_down_until:
        return _fallback_is_limited(client_ip)

    window_index = int(now // WINDOW_SECONDS)
    key = f"ratelimit:{client_ip}:{window_index}"

    try:
        client = _get_client()
        count = client.incr(key)
        if count == 1:
            client.expire(key, WINDOW_SECONDS)
        return count > MAX_REQUESTS_PER_WINDOW
    except redis.RedisError as exc:
        logger.warning(
            "Redis unavailable for rate limiting (%s) — using in-memory fallback for the next %ds",
            exc, REDIS_DOWN_COOLDOWN_SECONDS,
        )
        _redis_down_until = now + REDIS_DOWN_COOLDOWN_SECONDS
        return _fallback_is_limited(client_ip)
