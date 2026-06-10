# -*- coding: utf-8 -*-

import time

from rate_limiter import RateLimiter


def test_rate_limiter_disabled():
    limiter = RateLimiter(0)
    start = time.monotonic()
    for _ in range(5):
        limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 0.2


def test_rate_limiter_enforces_interval():
    limiter = RateLimiter(2.0)
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.4
