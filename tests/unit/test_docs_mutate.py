"""Tests for suitewright.docs.mutate — guarded_mutate and write helpers."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from suitewright._core.cache import CacheStore
from suitewright.docs.mutate import guarded_mutate


@pytest.fixture()
def cache_store(tmp_path, monkeypatch):
    """Create a CacheStore("docs") with cache_dir pointing to tmp_path."""
    monkeypatch.setenv("SUITEWRIGHT_CACHE_DIR", str(tmp_path))
    return CacheStore("docs")


@pytest.fixture()
def sample_doc():
    """A sample Google Docs API response with revisionId."""
    return {
        "documentId": "doc-mut-001",
        "title": "Mutate Test Document",
        "revisionId": "rev-original",
        "suggestionsViewMode": "SUGGESTIONS_INLINE",
        "body": {
            "content": [
                {"sectionBreak": {}, "startIndex": 0, "endIndex": 1},
                {
                    "startIndex": 1,
                    "endIndex": 20,
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 1,
                                "endIndex": 20,
                                "textRun": {"content": "Hello world text.\n", "textStyle": {}},
                            }
                        ],
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    },
                },
            ]
        },
    }


@pytest.fixture()
def sample_doc_no_revision():
    """A sample Google Docs API response without revisionId (viewer access)."""
    return {
        "documentId": "doc-viewer-mut",
        "title": "Viewer Mutate Document",
        "suggestionsViewMode": "SUGGESTIONS_INLINE",
        "body": {
            "content": [
                {"sectionBreak": {}, "startIndex": 0, "endIndex": 1},
                {
                    "startIndex": 1,
                    "endIndex": 10,
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 1,
                                "endIndex": 10,
                                "textRun": {"content": "Content\n", "textStyle": {}},
                            }
                        ],
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    },
                },
            ]
        },
    }


class TestGuardedMutateValidation:
    """guarded_mutate validates cache exists before executing."""

    def test_exits_when_cache_missing(self, cache_store, monkeypatch, capsys):
        monkeypatch.setattr("suitewright.docs.mutate._cache", cache_store)

        requests = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        with pytest.raises(SystemExit):
            guarded_mutate("nonexistent-doc", requests)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["code"] == "CACHE_MISSING"
        assert err_output["status"] == "error"

    @patch("suitewright.docs.mutate.build_service")
    @patch("suitewright.docs.mutate.execute_with_backoff")
    def test_validates_staleness_before_execute(
        self, mock_backoff, mock_service, cache_store, sample_doc, monkeypatch, capsys
    ):
        """guarded_mutate checks revisionId against live before executing."""
        monkeypatch.setattr("suitewright.docs.mutate._cache", cache_store)
        cache_store.write("doc-mut-001", sample_doc)

        # Live revision differs → should abort
        mock_backoff.return_value = {"revisionId": "rev-different"}

        requests = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        with pytest.raises(SystemExit):
            guarded_mutate("doc-mut-001", requests)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["status"] == "stale"
        assert err_output["code"] == "REVISION_MISMATCH"
        assert err_output["cachedRevision"] == "rev-original"
        assert err_output["liveRevision"] == "rev-different"


class TestGuardedMutateDryRun:
    """dry-run returns without making API call."""

    @patch("suitewright.docs.mutate.build_service")
    @patch("suitewright.docs.mutate.execute_with_backoff")
    def test_dry_run_returns_requests_without_api_call(
        self, mock_backoff, mock_service, cache_store, sample_doc, monkeypatch
    ):
        monkeypatch.setattr("suitewright.docs.mutate._cache", cache_store)
        cache_store.write("doc-mut-001", sample_doc)

        # Staleness check returns matching revision
        mock_backoff.return_value = {"revisionId": "rev-original"}

        requests = [{"replaceAllText": {"containsText": {"text": "old"}, "replaceText": "new"}}]
        result = guarded_mutate("doc-mut-001", requests, dry_run=True)

        assert result["status"] == "dry-run"
        assert result["requestCount"] == 1
        assert result["requests"] == requests
        # Only 1 call for staleness check, no batchUpdate or re-fetch
        assert mock_backoff.call_count == 1

    @patch("suitewright.docs.mutate.build_service")
    @patch("suitewright.docs.mutate.execute_with_backoff")
    def test_dry_run_without_revision_id_makes_no_api_calls(
        self, mock_backoff, mock_service, cache_store, sample_doc_no_revision, monkeypatch
    ):
        monkeypatch.setattr("suitewright.docs.mutate._cache", cache_store)
        cache_store.write("doc-viewer-mut", sample_doc_no_revision)

        requests = [{"insertText": {"text": "hello", "location": {"index": 1}}}]
        result = guarded_mutate("doc-viewer-mut", requests, dry_run=True)

        assert result["status"] == "dry-run"
        assert result["requestCount"] == 1
        # No API calls at all (no revisionId → no staleness check)
        assert mock_backoff.call_count == 0


class TestWriteControlPresence:
    """writeControl present when revisionId available, absent when not."""

    @patch("suitewright.docs.mutate.fetch_doc")
    @patch("suitewright.docs.mutate.build_service")
    @patch("suitewright.docs.mutate.execute_with_backoff")
    def test_write_control_included_when_revision_id_present(
        self, mock_backoff, mock_service, mock_fetch, cache_store, sample_doc, monkeypatch
    ):
        monkeypatch.setattr("suitewright.docs.mutate._cache", cache_store)
        cache_store.write("doc-mut-001", sample_doc)

        fresh_doc = {**sample_doc, "revisionId": "rev-after"}
        mock_backoff.side_effect = [
            {"revisionId": "rev-original"},  # staleness check
            {"documentId": "doc-mut-001", "replies": []},  # batchUpdate
        ]
        mock_fetch.return_value = fresh_doc

        requests = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        guarded_mutate("doc-mut-001", requests)

        # We check the batchUpdate was called (2 backoff calls + fetch_doc)
        assert mock_backoff.call_count == 2
        assert mock_fetch.call_count == 1

    @patch("suitewright.docs.mutate.fetch_doc")
    @patch("suitewright.docs.mutate.build_service")
    @patch("suitewright.docs.mutate.execute_with_backoff")
    def test_write_control_absent_when_no_revision_id(
        self,
        mock_backoff,
        mock_service,
        mock_fetch,
        cache_store,
        sample_doc_no_revision,
        monkeypatch,
    ):
        monkeypatch.setattr("suitewright.docs.mutate._cache", cache_store)
        cache_store.write("doc-viewer-mut", sample_doc_no_revision)

        fresh_doc = {**sample_doc_no_revision}
        mock_backoff.side_effect = [
            {"documentId": "doc-viewer-mut", "replies": []},  # batchUpdate (no staleness check)
        ]
        mock_fetch.return_value = fresh_doc

        requests = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        guarded_mutate("doc-viewer-mut", requests)

        # Only 1 backoff call (batchUpdate), no staleness check
        assert mock_backoff.call_count == 1
        assert mock_fetch.call_count == 1

    def test_build_batch_update_body_includes_write_control(self):
        """Verify _build_batch_update_body includes writeControl with revisionId."""
        from suitewright.docs.state import _build_batch_update_body

        requests = [{"replaceAllText": {"containsText": {"text": "a"}, "replaceText": "b"}}]
        body = _build_batch_update_body(requests, "rev-123")

        assert body["writeControl"] == {"requiredRevisionId": "rev-123"}
        assert body["requests"] == requests

    def test_build_batch_update_body_omits_write_control_when_none(self):
        """Verify _build_batch_update_body omits writeControl when revisionId is None."""
        from suitewright.docs.state import _build_batch_update_body

        requests = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        body = _build_batch_update_body(requests, None)

        assert "writeControl" not in body
        assert body["requests"] == requests


class TestCacheRefreshAfterSuccess:
    """Cache is refreshed after a successful mutation."""

    @patch("suitewright.docs.mutate.fetch_doc")
    @patch("suitewright.docs.mutate.build_service")
    @patch("suitewright.docs.mutate.execute_with_backoff")
    def test_cache_updated_with_fresh_doc_after_mutation(
        self, mock_backoff, mock_service, mock_fetch, cache_store, sample_doc, monkeypatch
    ):
        monkeypatch.setattr("suitewright.docs.mutate._cache", cache_store)
        cache_store.write("doc-mut-001", sample_doc)

        fresh_doc = {
            "documentId": "doc-mut-001",
            "title": "Updated Title After Mutation",
            "revisionId": "rev-after-mutation",
            "body": {"content": []},
        }
        mock_backoff.side_effect = [
            {"revisionId": "rev-original"},  # staleness check
            {"documentId": "doc-mut-001", "replies": []},  # batchUpdate
        ]
        mock_fetch.return_value = fresh_doc

        requests = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        result = guarded_mutate("doc-mut-001", requests)

        # Verify result
        assert result["status"] == "updated"
        assert result["documentId"] == "doc-mut-001"
        assert result["revisionId"] == "rev-after-mutation"

        # Verify cache was refreshed
        loaded = cache_store.load("doc-mut-001")
        assert loaded["title"] == "Updated Title After Mutation"
        assert loaded["revisionId"] == "rev-after-mutation"

    @patch("suitewright.docs.mutate.fetch_doc")
    @patch("suitewright.docs.mutate.build_service")
    @patch("suitewright.docs.mutate.execute_with_backoff")
    def test_cache_not_refreshed_on_dry_run(
        self, mock_backoff, mock_service, mock_fetch, cache_store, sample_doc, monkeypatch
    ):
        monkeypatch.setattr("suitewright.docs.mutate._cache", cache_store)
        cache_store.write("doc-mut-001", sample_doc)

        mock_backoff.return_value = {"revisionId": "rev-original"}

        requests = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        guarded_mutate("doc-mut-001", requests, dry_run=True)

        # Cache should still have original content
        loaded = cache_store.load("doc-mut-001")
        assert loaded["title"] == "Mutate Test Document"
        assert loaded["revisionId"] == "rev-original"
        # fetch_doc should not have been called
        assert mock_fetch.call_count == 0
