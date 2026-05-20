"""Tests for auth.py pure helper functions."""

from __future__ import annotations

import pytest

from suitewright.auth import (
    _extract_code_and_state,
    _missing_scopes_from_payload,
    _token_scopes,
)
from suitewright.service import SCOPES


class TestTokenScopes:
    def test_space_separated_string(self):
        payload = {
            "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/drive"
        }
        result = _token_scopes(payload)
        assert "https://www.googleapis.com/auth/gmail.readonly" in result
        assert "https://www.googleapis.com/auth/drive" in result

    def test_list_of_scopes(self):
        payload = {"scopes": ["https://www.googleapis.com/auth/gmail.readonly"]}
        result = _token_scopes(payload)
        assert "https://www.googleapis.com/auth/gmail.readonly" in result

    def test_empty_payload(self):
        assert _token_scopes({}) == set()

    def test_prefers_scopes_over_scope(self):
        payload = {
            "scopes": ["https://www.googleapis.com/auth/drive"],
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
        }
        result = _token_scopes(payload)
        assert "https://www.googleapis.com/auth/drive" in result

    def test_strips_whitespace(self):
        payload = {"scope": "  https://www.googleapis.com/auth/drive  "}
        result = _token_scopes(payload)
        assert "https://www.googleapis.com/auth/drive" in result


class TestMissingScopesFromPayload:
    def test_all_scopes_present(self):
        payload = {"scopes": SCOPES}
        assert _missing_scopes_from_payload(payload) == []

    def test_some_missing(self):
        payload = {"scopes": [SCOPES[0]]}
        missing = _missing_scopes_from_payload(payload)
        assert len(missing) == len(SCOPES) - 1
        assert SCOPES[0] not in missing

    def test_all_missing(self):
        missing = _missing_scopes_from_payload({})
        assert missing == sorted(SCOPES)

    def test_result_is_sorted(self):
        payload = {"scopes": []}
        missing = _missing_scopes_from_payload(payload)
        assert missing == sorted(missing)


class TestExtractCodeAndState:
    def test_raw_code(self):
        code, state = _extract_code_and_state("4/0AX4XfWh...")
        assert code == "4/0AX4XfWh..."
        assert state is None

    def test_full_redirect_url(self):
        url = "http://localhost:1/?state=abc123&code=4%2F0AX4XfWh&scope=email"
        code, state = _extract_code_and_state(url)
        assert code == "4/0AX4XfWh"
        assert state == "abc123"

    def test_url_without_code_raises(self):
        url = "http://localhost:1/?state=abc123"
        with pytest.raises(SystemExit):
            _extract_code_and_state(url)

    def test_url_without_state(self):
        url = "http://localhost:1/?code=mycode"
        code, state = _extract_code_and_state(url)
        assert code == "mycode"
        assert state is None
