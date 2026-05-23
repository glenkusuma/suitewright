"""Tests for suitewright._core.output — JSON formatting, stderr output, and exit codes."""

from __future__ import annotations

import json

import pytest

from suitewright._core.output import emit_json, emit_text, error_exit, warn


class TestEmitJson:
    """Verify emit_json prints formatted JSON to stdout."""

    def test_pretty_prints_dict(self, capsys):
        data = {"status": "ok", "count": 3}
        emit_json(data)
        captured = capsys.readouterr()
        assert captured.out == json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        assert captured.err == ""

    def test_pretty_prints_list(self, capsys):
        data = [{"id": 1}, {"id": 2}]
        emit_json(data)
        captured = capsys.readouterr()
        assert captured.out == json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    def test_compact_mode_single_line(self, capsys):
        data = {"status": "ok", "items": [1, 2, 3]}
        emit_json(data, compact=True)
        captured = capsys.readouterr()
        # Compact mode: no indentation, single line
        assert "\n" not in captured.out.strip()
        assert json.loads(captured.out) == data

    def test_ensure_ascii_false(self, capsys):
        data = {"title": "Ünïcödé テスト"}
        emit_json(data)
        captured = capsys.readouterr()
        # Non-ASCII characters should appear directly, not escaped
        assert "Ünïcödé テスト" in captured.out

    def test_output_is_valid_json(self, capsys):
        data = {"nested": {"key": [1, 2, 3]}, "flag": True, "empty": None}
        emit_json(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data

    def test_compact_output_is_valid_json(self, capsys):
        data = {"a": 1, "b": [2, 3]}
        emit_json(data, compact=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data


class TestEmitText:
    """Verify emit_text prints plain text to stdout without trailing newline."""

    def test_prints_text_without_trailing_newline(self, capsys):
        emit_text("hello world")
        captured = capsys.readouterr()
        assert captured.out == "hello world"
        assert captured.err == ""

    def test_preserves_embedded_newlines(self, capsys):
        emit_text("line1\nline2\nline3")
        captured = capsys.readouterr()
        assert captured.out == "line1\nline2\nline3"

    def test_empty_string(self, capsys):
        emit_text("")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestErrorExit:
    """Verify error_exit prints JSON to stderr and raises SystemExit(1)."""

    def test_exits_with_code_1(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            error_exit("error", "NOT_FOUND", "Resource not found")
        assert exc_info.value.code == 1

    def test_outputs_json_to_stderr(self, capsys):
        with pytest.raises(SystemExit):
            error_exit("stale", "REVISION_MISMATCH", "Document changed.")
        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert payload["status"] == "stale"
        assert payload["code"] == "REVISION_MISMATCH"
        assert payload["message"] == "Document changed."

    def test_includes_context_kwargs(self, capsys):
        with pytest.raises(SystemExit):
            error_exit(
                "stale",
                "REVISION_MISMATCH",
                "Document changed.",
                cachedRevision="abc",
                liveRevision="def",
            )
        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert payload["cachedRevision"] == "abc"
        assert payload["liveRevision"] == "def"

    def test_stderr_is_formatted_json(self, capsys):
        with pytest.raises(SystemExit):
            error_exit("error", "CACHE_MISSING", "Cache not found.")
        captured = capsys.readouterr()
        # Should be indented (indent=2)
        assert "  " in captured.err
        # Verify it's valid JSON
        json.loads(captured.err)


class TestWarn:
    """Verify warn prints JSON warning to stderr without exiting."""

    def test_outputs_to_stderr(self, capsys):
        warn("Something might be wrong")
        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert payload["warning"] == "Something might be wrong"

    def test_includes_context_kwargs(self, capsys):
        warn("No revisionId", documentId="doc123", fallback="cacheHash")
        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert payload["warning"] == "No revisionId"
        assert payload["documentId"] == "doc123"
        assert payload["fallback"] == "cacheHash"

    def test_does_not_exit(self, capsys):
        # warn should return normally, not raise SystemExit
        warn("Non-fatal warning")
        # If we get here, no exception was raised
        captured = capsys.readouterr()
        assert "warning" in captured.err

    def test_warn_is_compact_json(self, capsys):
        warn("test message")
        captured = capsys.readouterr()
        # warn uses compact (no indent) format
        lines = captured.err.strip().split("\n")
        assert len(lines) == 1
