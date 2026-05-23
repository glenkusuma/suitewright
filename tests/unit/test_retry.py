"""Tests for suitewright.retry — exponential backoff behavior."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from googleapiclient.errors import HttpError

from suitewright._core.retry import execute_with_backoff


class FakeResp:
    """Minimal response object mimicking httplib2.Response."""

    def __init__(self, status: int):
        self.status = status
        self.reason = "error"


def _make_http_error(status: int):
    """Create a googleapiclient HttpError with the given status code."""
    from googleapiclient.errors import HttpError

    resp = FakeResp(status)
    return HttpError(resp=resp, content=b"error")


class TestSuccessOnFirstAttempt:
    def test_returns_result_immediately(self):
        result = execute_with_backoff(lambda: 42)
        assert result == 42

    def test_returns_complex_result(self):
        data = {"status": "ok", "items": [1, 2, 3]}
        result = execute_with_backoff(lambda: data)
        assert result == data


class TestRetryOnTransientErrors:
    @patch("suitewright._core.retry.time.sleep")
    def test_retries_on_429(self, mock_sleep):
        calls = {"count": 0}

        def flaky():
            calls["count"] += 1
            if calls["count"] < 3:
                raise _make_http_error(429)
            return "success"

        result = execute_with_backoff(flaky, base_delay=1.0)
        assert result == "success"
        assert calls["count"] == 3
        # Should have slept twice (before attempt 2 and 3)
        assert mock_sleep.call_count == 2

    @patch("suitewright._core.retry.time.sleep")
    def test_retries_on_500(self, mock_sleep):
        calls = {"count": 0}

        def flaky():
            calls["count"] += 1
            if calls["count"] < 2:
                raise _make_http_error(500)
            return "ok"

        result = execute_with_backoff(flaky, base_delay=1.0)
        assert result == "ok"
        assert calls["count"] == 2

    @patch("suitewright._core.retry.time.sleep")
    def test_retries_on_502(self, mock_sleep):
        calls = {"count": 0}

        def flaky():
            calls["count"] += 1
            if calls["count"] < 2:
                raise _make_http_error(502)
            return "ok"

        result = execute_with_backoff(flaky, base_delay=1.0)
        assert result == "ok"

    @patch("suitewright._core.retry.time.sleep")
    def test_retries_on_503(self, mock_sleep):
        calls = {"count": 0}

        def flaky():
            calls["count"] += 1
            if calls["count"] < 2:
                raise _make_http_error(503)
            return "ok"

        result = execute_with_backoff(flaky, base_delay=1.0)
        assert result == "ok"

    @patch("suitewright._core.retry.time.sleep")
    def test_retries_on_504(self, mock_sleep):
        calls = {"count": 0}

        def flaky():
            calls["count"] += 1
            if calls["count"] < 2:
                raise _make_http_error(504)
            return "ok"

        result = execute_with_backoff(flaky, base_delay=1.0)
        assert result == "ok"


class TestExponentialBackoffDelays:
    @patch("suitewright._core.retry.time.sleep")
    def test_delays_are_exponential(self, mock_sleep):
        calls = {"count": 0}

        def always_fail():
            calls["count"] += 1
            raise _make_http_error(429)

        with pytest.raises(HttpError):
            execute_with_backoff(always_fail, retries=3, base_delay=1.5)

        # Delays: 1.5*2^0=1.5, 1.5*2^1=3.0, 1.5*2^2=6.0
        assert mock_sleep.call_count == 3
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.5, 3.0, 6.0]

    @patch("suitewright._core.retry.time.sleep")
    def test_default_delays(self, mock_sleep):
        """Default: retries=4, base_delay=1.5 → delays 1.5, 3, 6, 12."""
        calls = {"count": 0}

        def always_fail():
            calls["count"] += 1
            raise _make_http_error(500)

        with pytest.raises(HttpError):
            execute_with_backoff(always_fail)

        assert mock_sleep.call_count == 4
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.5, 3.0, 6.0, 12.0]


class TestMaxAttempts:
    @patch("suitewright._core.retry.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        """After retries+1 total attempts, the error is raised."""

        def always_fail():
            raise _make_http_error(429)

        with pytest.raises(HttpError) as exc_info:
            execute_with_backoff(always_fail, retries=4, base_delay=0.1)

        assert exc_info.value.resp.status == 429

    @patch("suitewright._core.retry.time.sleep")
    def test_total_attempts_equals_retries_plus_one(self, mock_sleep):
        calls = {"count": 0}

        def always_fail():
            calls["count"] += 1
            raise _make_http_error(503)

        with pytest.raises(HttpError):
            execute_with_backoff(always_fail, retries=2, base_delay=0.1)

        # 1 initial + 2 retries = 3 total attempts
        assert calls["count"] == 3


class TestNonRetryableErrors:
    def test_400_raises_immediately(self):
        from googleapiclient.errors import HttpError

        calls = {"count": 0}

        def bad_request():
            calls["count"] += 1
            raise _make_http_error(400)

        with pytest.raises(HttpError) as exc_info:
            execute_with_backoff(bad_request)

        assert exc_info.value.resp.status == 400
        assert calls["count"] == 1  # No retries

    def test_401_raises_immediately(self):
        from googleapiclient.errors import HttpError

        calls = {"count": 0}

        def unauthorized():
            calls["count"] += 1
            raise _make_http_error(401)

        with pytest.raises(HttpError) as exc_info:
            execute_with_backoff(unauthorized)

        assert exc_info.value.resp.status == 401
        assert calls["count"] == 1

    def test_403_raises_immediately(self):
        from googleapiclient.errors import HttpError

        calls = {"count": 0}

        def forbidden():
            calls["count"] += 1
            raise _make_http_error(403)

        with pytest.raises(HttpError) as exc_info:
            execute_with_backoff(forbidden)

        assert exc_info.value.resp.status == 403
        assert calls["count"] == 1

    def test_404_raises_immediately(self):
        from googleapiclient.errors import HttpError

        calls = {"count": 0}

        def not_found():
            calls["count"] += 1
            raise _make_http_error(404)

        with pytest.raises(HttpError) as exc_info:
            execute_with_backoff(not_found)

        assert exc_info.value.resp.status == 404
        assert calls["count"] == 1


class TestNonHttpErrors:
    @patch("suitewright._core.retry.time.sleep")
    def test_generic_exception_retries(self, mock_sleep):
        """Non-HttpError exceptions are retried (e.g., network timeouts)."""
        calls = {"count": 0}

        def flaky():
            calls["count"] += 1
            if calls["count"] < 3:
                raise ConnectionError("network timeout")
            return "recovered"

        result = execute_with_backoff(flaky, retries=4, base_delay=0.1)
        assert result == "recovered"
        assert calls["count"] == 3

    @patch("suitewright._core.retry.time.sleep")
    def test_generic_exception_raises_after_max_retries(self, mock_sleep):
        def always_fail():
            raise TimeoutError("timed out")

        with pytest.raises(TimeoutError, match="timed out"):
            execute_with_backoff(always_fail, retries=2, base_delay=0.1)
