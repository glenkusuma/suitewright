"""Tests for suitewright._core.update_check - PyPI version check."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

from suitewright import __version__
from suitewright._core.update_check import (
    _is_newer,
    _read_cache,
    _write_cache,
    check_for_update,
)


class TestIsNewer:
    def test_newer_version_returns_true(self):
        assert _is_newer("0.0.3", "0.0.2") is True

    def test_same_version_returns_false(self):
        assert _is_newer("0.0.2", "0.0.2") is False

    def test_older_version_returns_false(self):
        assert _is_newer("0.0.1", "0.0.2") is False

    def test_major_bump(self):
        assert _is_newer("1.0.0", "0.9.9") is True

    def test_prerelease_vs_release(self):
        assert _is_newer("0.0.2", "0.0.2rc1") is True


class TestCache:
    def test_write_then_read(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        _write_cache("1.2.3")
        cached = _read_cache()
        assert cached is not None
        assert cached["latest"] == "1.2.3"

    def test_expired_cache_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        cache_file = tmp_path / "suitewright" / "update-check.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({
            "latest": "1.0.0",
            "checked_at": time.time() - 90000,
        }))
        assert _read_cache() is None

    def test_fresh_cache_returns_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        cache_file = tmp_path / "suitewright" / "update-check.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({
            "latest": "2.0.0",
            "checked_at": time.time() - 100,
        }))
        cached = _read_cache()
        assert cached["latest"] == "2.0.0"

    def test_missing_cache_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert _read_cache() is None


class TestCheckForUpdate:
    def test_prints_notice_when_newer_available(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.delenv("SUITEWRIGHT_NO_UPDATE_CHECK", raising=False)

        with patch(
            "suitewright._core.update_check._fetch_latest", return_value="9.9.9"
        ):
            check_for_update(__version__)

        captured = capsys.readouterr()
        assert "Update available" in captured.err
        assert "9.9.9" in captured.err
        assert "pip install --upgrade suitewright" in captured.err

    def test_no_notice_when_up_to_date(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.delenv("SUITEWRIGHT_NO_UPDATE_CHECK", raising=False)

        with patch(
            "suitewright._core.update_check._fetch_latest", return_value=__version__
        ):
            check_for_update(__version__)

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_no_notice_when_fetch_fails(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.delenv("SUITEWRIGHT_NO_UPDATE_CHECK", raising=False)

        with patch(
            "suitewright._core.update_check._fetch_latest", return_value=None
        ):
            check_for_update(__version__)

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_disabled_via_env_var(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.setenv("SUITEWRIGHT_NO_UPDATE_CHECK", "1")

        with patch(
            "suitewright._core.update_check._fetch_latest", return_value="9.9.9"
        ) as mock_fetch:
            check_for_update(__version__)

        captured = capsys.readouterr()
        assert captured.err == ""
        mock_fetch.assert_not_called()

    def test_uses_cache_instead_of_fetching(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.delenv("SUITEWRIGHT_NO_UPDATE_CHECK", raising=False)

        # Pre-populate cache with a newer version
        cache_file = tmp_path / "suitewright" / "update-check.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({
            "latest": "5.0.0",
            "checked_at": time.time(),
        }))

        with patch(
            "suitewright._core.update_check._fetch_latest"
        ) as mock_fetch:
            check_for_update(__version__)

        # Should not have called fetch (used cache)
        mock_fetch.assert_not_called()
        captured = capsys.readouterr()
        assert "5.0.0" in captured.err

    def test_never_crashes_on_exception(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.delenv("SUITEWRIGHT_NO_UPDATE_CHECK", raising=False)

        with patch(
            "suitewright._core.update_check._fetch_latest",
            side_effect=RuntimeError("network down"),
        ):
            check_for_update(__version__)

        # Should not raise, just silently skip
        captured = capsys.readouterr()
        assert captured.err == ""
