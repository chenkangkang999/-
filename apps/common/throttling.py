"""Atomic Redis token bucket; explicit single-process development alternative."""

from __future__ import annotations

import math
import threading
import time

from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.throttling import BaseThrottle

_lock = threading.Lock()
_buckets = {}
LUA = """
local now = redis.call('TIME')
local stamp = tonumber(now[1]) + tonumber(now[2]) / 1000000
local capacity, refill = tonumber(ARGV[1]), tonumber(ARGV[2])
local old = redis.call('HMGET', KEYS[1], 'tokens', 'stamp')
local tokens = tonumber(old[1]) or capacity
local previous = tonumber(old[2]) or stamp
tokens = math.min(capacity, tokens + math.max(0, stamp-previous) * refill)
local wait = 0
if tokens >= 1 then tokens = tokens - 1 else wait = math.ceil((1-tokens)/refill*1000) end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'stamp', stamp)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity/refill*2))
return wait
"""


class RateLimiterUnavailable(APIException):
    status_code = 503
    default_detail = "限流服务不可用，请稍后重试；未发起模型调用。"
    default_code = "RATE_LIMITER_UNAVAILABLE"


def consume(key, capacity, refill, now=None):
    if capacity <= 0 or refill <= 0 or not math.isfinite(refill):
        raise RateLimiterUnavailable()
    backend = settings.TOKEN_BUCKET_BACKEND
    if backend == "redis":
        import redis

        try:
            client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
            return int(client.eval(LUA, 1, key, capacity, refill)) / 1000
        except redis.RedisError:
            raise RateLimiterUnavailable() from None
    if backend != "memory":
        raise RateLimiterUnavailable()
    stamp = time.monotonic() if now is None else now
    with _lock:
        if key not in _buckets and len(_buckets) >= settings.TOKEN_BUCKET_MAX_KEYS:
            expired = [k for k, (_, when) in _buckets.items() if stamp - when > capacity / refill * 2]
            for expired_key in expired:
                _buckets.pop(expired_key, None)
            if len(_buckets) >= settings.TOKEN_BUCKET_MAX_KEYS:
                raise RateLimiterUnavailable()
        tokens, previous = _buckets.get(key, (capacity, stamp))
        tokens = min(capacity, tokens + max(0, stamp - previous) * refill)
        wait = max(0, (1 - tokens) / refill) if tokens < 1 else 0
        _buckets[key] = (tokens if wait else tokens - 1, stamp)
        return wait


class ConsultationTokenBucket(BaseThrottle):
    def allow_request(self, request, view):
        self.retry_after = None
        if request.method != "POST" or not settings.TOKEN_BUCKET_ENABLED:
            return True
        if not request.user or not request.user.is_authenticated:
            return True  # Authentication/permission checks own this rejection.
        self.retry_after = consume(f"medical:bucket:consultation:{request.user.pk}",
                                   settings.TOKEN_BUCKET_CAPACITY, settings.TOKEN_BUCKET_REFILL_PER_SECOND)
        return self.retry_after <= 0

    def wait(self):
        return self.retry_after
