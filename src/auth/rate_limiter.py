# -*- coding: utf-8 -*-
"""
RateLimiter — 内存滑动窗口限流器
================================

来源: backend/utils/security.py (merged)
"""
import time
from typing import Tuple, Optional


class RateLimiter:
    """基于滑动窗口的内存限流器。"""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict = {}

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """检查请求是否在限流范围内。

        Args:
            key: 限流键（通常是 user_id 或 IP）。

        Returns:
            (allowed, remaining_requests)
        """
        now = time.time()
        window_start = now - self.window_seconds

        if key in self._requests:
            self._requests[key] = [
                t for t in self._requests[key] if t > window_start
            ]
        else:
            self._requests[key] = []

        if len(self._requests[key]) >= self.max_requests:
            return False, 0

        self._requests[key].append(now)
        remaining = self.max_requests - len(self._requests[key])
        return True, remaining

    def reset(self, key: str = None):
        """重置限流计数。"""
        if key:
            self._requests.pop(key, None)
        else:
            self._requests.clear()


# 单例
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(max_requests: int = 30, window_seconds: int = 60) -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
    return _rate_limiter
