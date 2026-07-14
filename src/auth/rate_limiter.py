"""Bounded request and concurrency controls for public HTTP surfaces."""

from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class RateLimitBackendUnavailable(RuntimeError):
    """Raised when a configured shared limiter cannot make a decision."""


_REDIS_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    redis.call('PEXPIRE', key, window)
    return {0, count, oldest[2] or now}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return {1, count + 1, 0}
"""


class RateLimiter:
    """Sliding-window limiter with a Redis or bounded in-memory backend."""

    def __init__(
        self,
        max_requests: int = 30,
        window_seconds: int = 60,
        *,
        redis_client=None,
        namespace: str = "default",
        clock: Callable[[], float] = time.time,
        max_keys: int = 10_000,
    ) -> None:
        self.max_requests = max(1, int(max_requests))
        self.window_seconds = max(1, int(window_seconds))
        self.redis_client = redis_client
        self.namespace = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in str(namespace or "default")
        )
        self.clock = clock
        self.max_keys = max(100, int(max_keys))
        self._requests: dict[str, list[float]] = {}
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> RateLimitDecision:
        normalized_key = str(key or "anonymous")
        if self.redis_client is not None:
            return self._check_redis(normalized_key)
        return self._check_memory(normalized_key)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Compatibility wrapper for older callers."""
        decision = self.check(key)
        return decision.allowed, decision.remaining

    def _check_redis(self, key: str) -> RateLimitDecision:
        now_ms = int(self.clock() * 1000)
        window_ms = self.window_seconds * 1000
        redis_key = f"eduagent:rate-limit:{self.namespace}:{key}"
        member = f"{now_ms}:{uuid.uuid4().hex}"
        try:
            result = self.redis_client.eval(
                _REDIS_SLIDING_WINDOW,
                1,
                redis_key,
                now_ms,
                window_ms,
                self.max_requests,
                member,
            )
            allowed = bool(int(result[0]))
            count = int(result[1])
            oldest_ms = int(float(result[2] or 0))
        except Exception as exc:
            raise RateLimitBackendUnavailable("shared rate limiter unavailable") from exc
        retry_after = 0
        if not allowed:
            retry_after = max(1, math.ceil((oldest_ms + window_ms - now_ms) / 1000))
        return RateLimitDecision(
            allowed=allowed,
            limit=self.max_requests,
            remaining=max(0, self.max_requests - count),
            retry_after=retry_after,
        )

    def _check_memory(self, key: str) -> RateLimitDecision:
        now = float(self.clock())
        window_start = now - self.window_seconds
        with self._lock:
            requests = [timestamp for timestamp in self._requests.get(key, []) if timestamp > window_start]
            if len(requests) >= self.max_requests:
                self._requests[key] = requests
                self._last_seen[key] = now
                retry_after = max(1, math.ceil(requests[0] + self.window_seconds - now))
                return RateLimitDecision(False, self.max_requests, 0, retry_after)
            requests.append(now)
            self._requests[key] = requests
            self._last_seen[key] = now
            self._evict_keys_if_needed(exclude=key)
            return RateLimitDecision(
                True,
                self.max_requests,
                self.max_requests - len(requests),
                0,
            )

    def _evict_keys_if_needed(self, *, exclude: str) -> None:
        while len(self._requests) > self.max_keys:
            candidates = (
                (last_seen, candidate)
                for candidate, last_seen in self._last_seen.items()
                if candidate != exclude
            )
            try:
                _last_seen, oldest_key = min(candidates)
            except ValueError:
                return
            self._requests.pop(oldest_key, None)
            self._last_seen.pop(oldest_key, None)

    def reset(self, key: Optional[str] = None) -> None:
        if self.redis_client is not None:
            if key:
                try:
                    self.redis_client.delete(f"eduagent:rate-limit:{self.namespace}:{key}")
                except Exception as exc:
                    raise RateLimitBackendUnavailable("shared rate limiter unavailable") from exc
            return
        with self._lock:
            if key:
                self._requests.pop(key, None)
                self._last_seen.pop(key, None)
            else:
                self._requests.clear()
                self._last_seen.clear()


class KeyedConcurrencyLimiter:
    """Bound concurrent work per opaque subject without retaining idle keys."""

    def __init__(self, max_concurrent: int = 1) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self._active: dict[str, int] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str) -> bool:
        normalized_key = str(key or "anonymous")
        with self._lock:
            active = self._active.get(normalized_key, 0)
            if active >= self.max_concurrent:
                return False
            self._active[normalized_key] = active + 1
            return True

    def release(self, key: str) -> None:
        normalized_key = str(key or "anonymous")
        with self._lock:
            active = self._active.get(normalized_key, 0)
            if active <= 1:
                self._active.pop(normalized_key, None)
            else:
                self._active[normalized_key] = active - 1


_rate_limiter: Optional[RateLimiter] = None
_singleton_lock = threading.Lock()


def get_rate_limiter(max_requests: int = 30, window_seconds: int = 60) -> RateLimiter:
    """Return the legacy default limiter; route-specific code should own its policy."""
    global _rate_limiter
    with _singleton_lock:
        if _rate_limiter is None:
            _rate_limiter = RateLimiter(max_requests=max_requests, window_seconds=window_seconds)
        return _rate_limiter
