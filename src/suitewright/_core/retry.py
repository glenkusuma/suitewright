"""Shared exponential backoff retry for Google API calls."""

from __future__ import annotations

import time


def execute_with_backoff(func, *, retries: int = 4, base_delay: float = 1.5):
    """Execute func with exponential backoff on transient HTTP errors.

    Retries on: 429, 500, 502, 503, 504
    Raises immediately on: 400, 401, 403, 404 (non-retryable)
    """
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = None

    last_error = None
    for attempt in range(retries + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if HttpError is not None and isinstance(exc, HttpError):
                status = getattr(getattr(exc, "resp", None), "status", None)
                if status not in {429, 500, 502, 503, 504} or attempt == retries:
                    raise
            elif attempt == retries:
                raise
            time.sleep(base_delay * (2**attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError("Backoff loop exited without result or captured error")
