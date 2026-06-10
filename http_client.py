# -*- coding: utf-8 -*-
"""Shared HTTP session with retry and proxy support."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests import Response
from requests.exceptions import ConnectionError, RequestException, Timeout

from rate_limiter import RateLimiter

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class ClientConfig:
    timeout: int = 30
    proxy: str | None = None
    retries: int = 3
    retry_backoff: float = 0.6
    rate_limit: float = 0.0


class HttpSession:
    """requests.Session wrapper with retries and optional proxy."""

    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        config: ClientConfig | None = None,
    ):
        self.config = config or ClientConfig()
        self.session = requests.Session()
        self._request_lock = threading.Lock()
        self._rate_limiter = RateLimiter(self.config.rate_limit)
        base_headers = {"User-Agent": DEFAULT_USER_AGENT}
        if headers:
            base_headers.update(headers)
        self.session.headers.update(base_headers)
        if self.config.proxy:
            self.session.proxies.update(
                {"http": self.config.proxy, "https": self.config.proxy}
            )

    @property
    def timeout(self) -> int:
        return self.config.timeout

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        kwargs.setdefault("timeout", self.config.timeout)
        last_error: Exception | None = None
        attempts = max(1, self.config.retries)

        for attempt in range(attempts):
            try:
                self._rate_limiter.wait()
                with self._request_lock:
                    response = self.session.request(method, url, **kwargs)
                if response.status_code in RETRY_STATUS_CODES and attempt < attempts - 1:
                    time.sleep(self.config.retry_backoff * (attempt + 1))
                    continue
                response.raise_for_status()
                return response
            except (Timeout, ConnectionError) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(self.config.retry_backoff * (attempt + 1))
                    continue
            except RequestException as exc:
                last_error = exc
                break

        if last_error:
            raise last_error
        raise RuntimeError(f"HTTP request failed: {method} {url}")

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)
