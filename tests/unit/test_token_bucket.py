from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import redis

from apps.common import throttling


@pytest.fixture(autouse=True)
def bucket_settings(settings):
    settings.TOKEN_BUCKET_ENABLED = True
    settings.TOKEN_BUCKET_BACKEND = "memory"
    settings.TOKEN_BUCKET_MAX_KEYS = 100
    with throttling._lock:
        throttling._buckets.clear()


def test_bucket_refills_and_isolates_users():
    assert throttling.consume("u1", 2, 0.5, now=0) == 0
    assert throttling.consume("u1", 2, 0.5, now=0) == 0
    assert throttling.consume("u1", 2, 0.5, now=0) == 2
    assert throttling.consume("u2", 2, 0.5, now=0) == 0
    assert throttling.consume("u1", 2, 0.5, now=2) == 0


def test_single_process_bucket_claim_is_atomic():
    with ThreadPoolExecutor(max_workers=10) as pool:
        values = list(pool.map(lambda _: throttling.consume("same", 4, 1, now=10), range(20)))
    assert values.count(0) == 4
    assert sum(v > 0 for v in values) == 16


def test_redis_failure_is_not_silently_allowed(settings, monkeypatch):
    settings.TOKEN_BUCKET_BACKEND = "redis"
    monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: (_ for _ in ()).throw(redis.ConnectionError()))
    with pytest.raises(throttling.RateLimiterUnavailable):
        throttling.consume("u", 1, 1)


def test_only_post_consumes_and_switch_is_explicit(settings):
    bucket = throttling.ConsultationTokenBucket()
    request = SimpleNamespace(method="GET", user=SimpleNamespace(pk=1, is_authenticated=True))
    assert bucket.allow_request(request, None)
    request.method = "POST"
    settings.TOKEN_BUCKET_CAPACITY = 1
    settings.TOKEN_BUCKET_REFILL_PER_SECOND = 0.01
    assert bucket.allow_request(request, None)
    assert not bucket.allow_request(request, None)
    assert bucket.wait() > 90
    settings.TOKEN_BUCKET_ENABLED = False
    assert bucket.allow_request(request, None)
