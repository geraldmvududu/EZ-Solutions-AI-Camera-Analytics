import fakeredis
import redis
import pytest

from app.core import rate_limit


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """Swap the module-level Redis client for an in-memory fake so these tests exercise
    the real INCR/EXPIRE logic without needing an actual Redis server, and reset any
    in-memory fallback state between tests."""
    fake_client = fakeredis.FakeRedis()
    monkeypatch.setattr(rate_limit, "_redis_client", fake_client)
    monkeypatch.setattr(rate_limit, "_fallback_counts", {})
    monkeypatch.setattr(rate_limit, "_redis_down_until", 0.0)
    yield fake_client


def test_requests_under_limit_are_allowed():
    for _ in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        assert rate_limit.is_rate_limited("1.2.3.4") is False


def test_requests_over_limit_are_blocked():
    for _ in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        rate_limit.is_rate_limited("1.2.3.4")
    assert rate_limit.is_rate_limited("1.2.3.4") is True


def test_different_ips_have_independent_counters():
    for _ in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        rate_limit.is_rate_limited("1.2.3.4")
    assert rate_limit.is_rate_limited("1.2.3.4") is True
    assert rate_limit.is_rate_limited("5.6.7.8") is False


def test_counter_is_shared_across_calls_like_it_would_be_across_replicas():
    """The whole point of moving to Redis: two independent call sites (standing in for
    two backend replicas) hitting the same key must share one counter."""
    half = rate_limit.MAX_REQUESTS_PER_WINDOW // 2
    for _ in range(half):
        rate_limit.is_rate_limited("9.9.9.9")  # "replica A"
    for _ in range(half):
        rate_limit.is_rate_limited("9.9.9.9")  # "replica B", same Redis-backed counter
    assert rate_limit.is_rate_limited("9.9.9.9") is True


def test_falls_back_to_in_memory_when_redis_unreachable(monkeypatch):
    monkeypatch.setattr(rate_limit, "_get_client", lambda: (_ for _ in ()).throw(redis.exceptions.ConnectionError("down")))

    # Should not raise, and should still enforce a limit via the in-memory fallback.
    for _ in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        assert rate_limit.is_rate_limited("10.0.0.1") is False
    assert rate_limit.is_rate_limited("10.0.0.1") is True


def test_does_not_retry_redis_on_every_call_during_cooldown(monkeypatch):
    """Regression test for a real bug found while measuring live request latency: the
    first version reattempted a real Redis connection on every single request, which
    pays a full connect-timeout (~2s measured on Windows) each time Redis is down —
    turning 'fail open' into 'every request hangs'. Once one call fails, subsequent
    calls within the cooldown window must skip _get_client() entirely."""
    call_count = 0

    def _raise():
        nonlocal call_count
        call_count += 1
        raise redis.exceptions.ConnectionError("down")

    monkeypatch.setattr(rate_limit, "_get_client", _raise)

    rate_limit.is_rate_limited("10.0.0.2")  # first call: pays the cost, trips the breaker
    assert call_count == 1

    for _ in range(10):
        rate_limit.is_rate_limited("10.0.0.2")
    assert call_count == 1  # no further attempts while the cooldown is active
