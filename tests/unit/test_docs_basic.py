"""Tests for docs.basic pure helpers."""

from __future__ import annotations

import types

import pytest

from suitewright.docs.basic import load_docs_requests, summarize_docs_requests


def _make_args(requests: str = "", requests_file: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(requests=requests, requests_file=requests_file)


class TestLoadDocsRequests:
    def test_inline_json(self):
        args = _make_args(requests='[{"insertText": {}}]')
        result = load_docs_requests(args)
        assert result == [{"insertText": {}}]

    def test_from_file(self, tmp_requests_file):
        path = tmp_requests_file([{"replaceAllText": {}}])
        args = _make_args(requests_file=path)
        result = load_docs_requests(args)
        assert result == [{"replaceAllText": {}}]

    def test_empty_list_valid(self):
        args = _make_args(requests="[]")
        assert load_docs_requests(args) == []

    def test_both_provided_raises(self):
        args = _make_args(requests="[]", requests_file="/some/path")
        with pytest.raises(SystemExit):
            load_docs_requests(args)

    def test_neither_provided_raises(self):
        args = _make_args()
        with pytest.raises(SystemExit):
            load_docs_requests(args)

    def test_invalid_json_inline_raises(self):
        args = _make_args(requests="{not valid json}")
        with pytest.raises(SystemExit):
            load_docs_requests(args)

    def test_invalid_json_file_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid}")
        args = _make_args(requests_file=str(bad))
        with pytest.raises(SystemExit):
            load_docs_requests(args)

    def test_not_a_list_raises(self):
        args = _make_args(requests='{"key": "value"}')
        with pytest.raises(SystemExit):
            load_docs_requests(args)

    def test_missing_file_raises(self):
        args = _make_args(requests_file="/nonexistent/path.json")
        with pytest.raises(SystemExit):
            load_docs_requests(args)


class TestSummarizeDocsRequests:
    def test_extracts_kinds(self):
        requests = [
            {"insertText": {"location": {"index": 1}, "text": "hi"}},
            {"replaceAllText": {}},
            {"updateTextStyle": {}},
        ]
        result = summarize_docs_requests(requests)
        assert result == [
            {"index": 0, "kind": "insertText"},
            {"index": 1, "kind": "replaceAllText"},
            {"index": 2, "kind": "updateTextStyle"},
        ]

    def test_empty_list(self):
        assert summarize_docs_requests([]) == []

    def test_empty_dict_marked_unknown(self):
        result = summarize_docs_requests([{}])
        assert result[0]["kind"] == "unknown"

    def test_non_dict_marked_unknown(self):
        result = summarize_docs_requests(["not a dict"])
        assert result[0]["kind"] == "unknown"
