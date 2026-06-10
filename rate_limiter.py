# -*- coding: utf-8 -*-
"""Simple thread-safe request rate limiter."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Enforce a minimum interval between operations (requests per second)."""

    def __init__(self, requests_per_second: float = 0.0):
        self._interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    @property
    def enabled(self) -> bool:
        return self._interval > 0

    def wait(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                time.sleep(self._next_allowed - now)
            self._next_allowed = time.monotonic() + self._interval
