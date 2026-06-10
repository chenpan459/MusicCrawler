# -*- coding: utf-8 -*-

import time
from unittest.mock import MagicMock, patch

from http_client import ClientConfig, HttpSession


def test_http_session_applies_rate_limit():
    config = ClientConfig(rate_limit=5.0, retries=1, timeout=5)
    session = HttpSession(config=config)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(session.session, "request", return_value=mock_response) as request_mock:
        start = time.monotonic()
        session.get("https://example.com/a")
        session.get("https://example.com/b")
        elapsed = time.monotonic() - start

    assert request_mock.call_count == 2
    assert elapsed >= 0.15
