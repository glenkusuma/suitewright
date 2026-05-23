"""Tests for suitewright.docs.state — cache lifecycle commands."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from suitewright._core.cache import CacheStore
from suitewright.docs.state import (
    _build_batch_update_body,
    cmd_fetch,
    cmd_show,
    cmd_update,
    cmd_validate,
    register,
)


@pytest.fixture()
def cache_store(tmp_path, monkeypatch):
    """Create a CacheStore("docs") with cache_dir pointing to tmp_path."""
    monkeypatch.setenv("SUITEWRIGHT_CACHE_DIR", str(tmp_path))
    return CacheStore("docs")


@pytest.fixture()
def sample_doc():
    """A sample Google Docs API response with revisionId."""
    return {
        "documentId": "doc-abc123",
        "title": "Test Document",
        "revisionId": "rev-xyz789",
        "suggestionsViewMode": "SUGGESTIONS_INLINE",
        "body": {"content": [{"sectionBreak": {}, "startIndex": 0, "endIndex": 1}]},
    }


@pytest.fixture()
def sample_doc_no_revision():
    """A sample Google Docs API response without revisionId (viewer access)."""
    return {
        "documentId": "doc-viewer",
        "title": "Viewer Document",
        "suggestionsViewMode": "SUGGESTIONS_INLINE",
        "body": {"content": [{"sectionBreak": {}, "startIndex": 0, "endIndex": 1}]},
    }


class TestCmdFetch:
    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_fetch_stores_document_in_cache(
        self, mock_backoff, mock_service, cache_store, sample_doc, monkeypatch
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        mock_backoff.return_value = sample_doc

        args = SimpleNamespace(doc_id="doc-abc123", compact=False)
        with patch("suitewright.docs.state.emit_json"):
            cmd_fetch(args)

        # Verify document was cached
        assert cache_store.exists("doc-abc123")
        loaded = cache_store.load("doc-abc123")
        assert loaded == sample_doc

    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_fetch_emits_status_with_revision_id(
        self, mock_backoff, mock_service, cache_store, sample_doc, monkeypatch, capsys
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        mock_backoff.return_value = sample_doc

        args = SimpleNamespace(doc_id="doc-abc123", compact=False)
        cmd_fetch(args)

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "cached"
        assert output["documentId"] == "doc-abc123"
        assert output["title"] == "Test Document"
        assert output["revisionId"] == "rev-xyz789"
        assert "cachePath" in output

    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_fetch_without_revision_id_emits_warning(
        self,
        mock_backoff,
        mock_service,
        cache_store,
        sample_doc_no_revision,
        monkeypatch,
        capsys,
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        mock_backoff.return_value = sample_doc_no_revision

        args = SimpleNamespace(doc_id="doc-viewer", compact=False)
        cmd_fetch(args)

        captured = capsys.readouterr()
        # Status output should not contain revisionId
        output = json.loads(captured.out)
        assert "revisionId" not in output
        # Warning should be on stderr
        warning = json.loads(captured.err)
        assert "revisionId absent" in warning["warning"]

    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_fetch_preserves_all_top_level_keys(
        self, mock_backoff, mock_service, cache_store, monkeypatch
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        doc = {
            "documentId": "doc-full",
            "title": "Full Doc",
            "revisionId": "rev-1",
            "suggestionsViewMode": "SUGGESTIONS_INLINE",
            "body": {"content": []},
            "documentStyle": {"marginTop": {}},
            "namedStyles": {"styles": []},
            "lists": {"list1": {}},
            "headers": {"h1": {}},
            "footers": {"f1": {}},
            "inlineObjects": {"obj1": {}},
            "positionedObjects": {"pos1": {}},
            "namedRanges": {"range1": {}},
        }
        mock_backoff.return_value = doc

        args = SimpleNamespace(doc_id="doc-full", compact=False)
        cmd_fetch(args)

        loaded = cache_store.load("doc-full")
        assert loaded == doc


class TestCmdShow:
    def test_show_returns_metadata(self, cache_store, sample_doc, monkeypatch, capsys):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        args = SimpleNamespace(doc_id="doc-abc123", compact=False)
        cmd_show(args)

        output = json.loads(capsys.readouterr().out)
        assert output["documentId"] == "doc-abc123"
        assert output["title"] == "Test Document"
        assert output["revisionId"] == "rev-xyz789"
        assert output["cacheHash"]  # non-empty hash
        assert "cachePath" in output

    def test_show_exits_when_cache_missing(self, cache_store, monkeypatch):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)

        args = SimpleNamespace(doc_id="nonexistent", compact=False)
        with pytest.raises(SystemExit):
            cmd_show(args)


class TestCmdValidate:
    def test_validate_returns_ok_status(self, cache_store, sample_doc, monkeypatch, capsys):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        args = SimpleNamespace(
            doc_id="doc-abc123", expected_revision="", expected_hash="", compact=False
        )
        cmd_validate(args)

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "ok"
        assert output["documentId"] == "doc-abc123"
        assert output["revisionId"] == "rev-xyz789"
        assert len(output["cacheHash"]) == 64

    def test_validate_with_matching_revision(self, cache_store, sample_doc, monkeypatch, capsys):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        args = SimpleNamespace(
            doc_id="doc-abc123",
            expected_revision="rev-xyz789",
            expected_hash="",
            compact=False,
        )
        cmd_validate(args)

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "ok"

    def test_validate_revision_mismatch_exits(self, cache_store, sample_doc, monkeypatch, capsys):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        args = SimpleNamespace(
            doc_id="doc-abc123",
            expected_revision="wrong-rev",
            expected_hash="",
            compact=False,
        )
        with pytest.raises(SystemExit):
            cmd_validate(args)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["status"] == "stale"
        assert err_output["code"] == "REVISION_MISMATCH"

    def test_validate_hash_mismatch_exits(self, cache_store, sample_doc, monkeypatch, capsys):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        args = SimpleNamespace(
            doc_id="doc-abc123",
            expected_revision="",
            expected_hash="0000000000000000000000000000000000000000000000000000000000000000",
            compact=False,
        )
        with pytest.raises(SystemExit):
            cmd_validate(args)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["status"] == "stale"
        assert err_output["code"] == "HASH_MISMATCH"

    def test_validate_with_matching_hash(self, cache_store, sample_doc, monkeypatch, capsys):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)
        expected_hash = cache_store.hash("doc-abc123")

        args = SimpleNamespace(
            doc_id="doc-abc123",
            expected_revision="",
            expected_hash=expected_hash,
            compact=False,
        )
        cmd_validate(args)

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "ok"

    def test_validate_without_revision_id_reports_null(
        self, cache_store, sample_doc_no_revision, monkeypatch, capsys
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-viewer", sample_doc_no_revision)

        args = SimpleNamespace(
            doc_id="doc-viewer", expected_revision="", expected_hash="", compact=False
        )
        cmd_validate(args)

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "ok"
        assert output["revisionId"] is None

    def test_validate_exits_when_cache_missing(self, cache_store, monkeypatch):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)

        args = SimpleNamespace(
            doc_id="nonexistent", expected_revision="", expected_hash="", compact=False
        )
        with pytest.raises(SystemExit):
            cmd_validate(args)


class TestRegister:
    def test_register_adds_fetch_show_validate(self):
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        register(sub)

        # Verify subcommands are registered
        choices = sub.choices
        assert "fetch" in choices
        assert "show" in choices
        assert "validate" in choices

    def test_fetch_parser_has_doc_id_argument(self):
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        register(sub)

        # Parse a fetch command
        args = parser.parse_args(["fetch", "my-doc-id"])
        assert args.doc_id == "my-doc-id"
        assert hasattr(args, "func")

    def test_validate_parser_has_expected_flags(self):
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        register(sub)

        args = parser.parse_args(
            ["validate", "my-doc-id", "--expected-revision", "rev-1", "--expected-hash", "abc"]
        )
        assert args.doc_id == "my-doc-id"
        assert args.expected_revision == "rev-1"
        assert args.expected_hash == "abc"


class TestBuildBatchUpdateBody:
    def test_includes_write_control_when_revision_id_present(self):
        requests = [{"replaceAllText": {"containsText": {"text": "old"}, "replaceText": "new"}}]
        body = _build_batch_update_body(requests, "rev-abc")

        assert body["requests"] == requests
        assert body["writeControl"] == {"requiredRevisionId": "rev-abc"}

    def test_omits_write_control_when_revision_id_none(self):
        requests = [{"insertText": {"text": "hello", "location": {"index": 1}}}]
        body = _build_batch_update_body(requests, None)

        assert body["requests"] == requests
        assert "writeControl" not in body

    def test_omits_write_control_when_revision_id_empty_string(self):
        requests = [{"insertText": {"text": "hello", "location": {"index": 1}}}]
        body = _build_batch_update_body(requests, "")

        assert body["requests"] == requests
        assert "writeControl" not in body


class TestCmdUpdate:
    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_update_with_revision_id_includes_write_control(
        self, mock_backoff, mock_service, cache_store, sample_doc, monkeypatch, capsys, tmp_path
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        # Create requests file
        requests_file = tmp_path / "requests.json"
        requests_data = [
            {"replaceAllText": {"containsText": {"text": "old"}, "replaceText": "new"}}
        ]
        requests_file.write_text(json.dumps(requests_data))

        # Mock: staleness check returns same revision, batchUpdate succeeds,
        # re-fetch returns fresh doc
        fresh_doc = {**sample_doc, "revisionId": "rev-new"}
        mock_backoff.side_effect = [
            {"revisionId": "rev-xyz789"},  # staleness check
            {"documentId": "doc-abc123", "replies": []},  # batchUpdate result
            fresh_doc,  # re-fetch
        ]

        args = SimpleNamespace(
            doc_id="doc-abc123", requests_file=str(requests_file), dry_run=False, compact=False
        )
        cmd_update(args)

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "updated"
        assert output["documentId"] == "doc-abc123"
        assert output["revisionId"] == "rev-new"
        assert "cachePath" in output

    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_update_stale_revision_aborts(
        self, mock_backoff, mock_service, cache_store, sample_doc, monkeypatch, capsys, tmp_path
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        requests_file = tmp_path / "requests.json"
        insert_req = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        requests_file.write_text(json.dumps(insert_req))

        # Live revision differs from cached
        mock_backoff.return_value = {"revisionId": "rev-different"}

        args = SimpleNamespace(
            doc_id="doc-abc123", requests_file=str(requests_file), dry_run=False, compact=False
        )
        with pytest.raises(SystemExit):
            cmd_update(args)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["status"] == "stale"
        assert err_output["code"] == "REVISION_MISMATCH"
        assert err_output["cachedRevision"] == "rev-xyz789"
        assert err_output["liveRevision"] == "rev-different"

    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_update_without_revision_id_emits_warning(
        self,
        mock_backoff,
        mock_service,
        cache_store,
        sample_doc_no_revision,
        monkeypatch,
        capsys,
        tmp_path,
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-viewer", sample_doc_no_revision)

        requests_file = tmp_path / "requests.json"
        insert_req = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        requests_file.write_text(json.dumps(insert_req))

        fresh_doc = {**sample_doc_no_revision}
        mock_backoff.side_effect = [
            {"documentId": "doc-viewer", "replies": []},  # batchUpdate (no staleness check)
            fresh_doc,  # re-fetch
        ]

        args = SimpleNamespace(
            doc_id="doc-viewer", requests_file=str(requests_file), dry_run=False, compact=False
        )
        cmd_update(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "updated"
        # Warning about no revisionId should be on stderr
        warning = json.loads(captured.err)
        assert "No revisionId" in warning["warning"]

    def test_update_missing_requests_file_exits(self, cache_store, sample_doc, monkeypatch, capsys):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        args = SimpleNamespace(
            doc_id="doc-abc123",
            requests_file="/nonexistent/path/requests.json",
            dry_run=False,
            compact=False,
        )
        with pytest.raises(SystemExit):
            cmd_update(args)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["code"] == "FILE_NOT_FOUND"

    def test_update_invalid_json_exits(
        self, cache_store, sample_doc, monkeypatch, capsys, tmp_path
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        requests_file = tmp_path / "bad.json"
        requests_file.write_text("not valid json {{{")

        args = SimpleNamespace(
            doc_id="doc-abc123", requests_file=str(requests_file), dry_run=False, compact=False
        )
        with pytest.raises(SystemExit):
            cmd_update(args)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["code"] == "INVALID_JSON"

    def test_update_non_array_json_exits(
        self, cache_store, sample_doc, monkeypatch, capsys, tmp_path
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        requests_file = tmp_path / "obj.json"
        requests_file.write_text(json.dumps({"not": "an array"}))

        args = SimpleNamespace(
            doc_id="doc-abc123", requests_file=str(requests_file), dry_run=False, compact=False
        )
        with pytest.raises(SystemExit):
            cmd_update(args)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["code"] == "INVALID_FORMAT"

    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_update_dry_run_does_not_execute(
        self, mock_backoff, mock_service, cache_store, sample_doc, monkeypatch, capsys, tmp_path
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        requests_file = tmp_path / "requests.json"
        requests_data = [
            {"replaceAllText": {"containsText": {"text": "old"}, "replaceText": "new"}}
        ]
        requests_file.write_text(json.dumps(requests_data))

        # Staleness check returns matching revision
        mock_backoff.return_value = {"revisionId": "rev-xyz789"}

        args = SimpleNamespace(
            doc_id="doc-abc123", requests_file=str(requests_file), dry_run=True, compact=False
        )
        cmd_update(args)

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "dry-run"
        assert output["requestCount"] == 1
        assert output["requests"] == requests_data
        assert output["writeControl"] == {"requiredRevisionId": "rev-xyz789"}

        # batchUpdate should NOT have been called (only 1 call for staleness check)
        assert mock_backoff.call_count == 1

    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_update_dry_run_without_revision_id(
        self,
        mock_backoff,
        mock_service,
        cache_store,
        sample_doc_no_revision,
        monkeypatch,
        capsys,
        tmp_path,
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-viewer", sample_doc_no_revision)

        requests_file = tmp_path / "requests.json"
        requests_data = [{"insertText": {"text": "hello", "location": {"index": 1}}}]
        requests_file.write_text(json.dumps(requests_data))

        args = SimpleNamespace(
            doc_id="doc-viewer", requests_file=str(requests_file), dry_run=True, compact=False
        )
        cmd_update(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "dry-run"
        assert output["requestCount"] == 1
        assert "writeControl" not in output
        # No API calls should have been made (no staleness check without revisionId)
        assert mock_backoff.call_count == 0

    def test_update_cache_missing_exits(self, cache_store, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)

        requests_file = tmp_path / "requests.json"
        insert_req = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        requests_file.write_text(json.dumps(insert_req))

        args = SimpleNamespace(
            doc_id="nonexistent", requests_file=str(requests_file), dry_run=False, compact=False
        )
        with pytest.raises(SystemExit):
            cmd_update(args)

        err_output = json.loads(capsys.readouterr().err)
        assert err_output["code"] == "CACHE_MISSING"

    @patch("suitewright.docs.state.build_service")
    @patch("suitewright.docs.state.execute_with_backoff")
    def test_update_refreshes_cache_after_success(
        self, mock_backoff, mock_service, cache_store, sample_doc, monkeypatch, capsys, tmp_path
    ):
        monkeypatch.setattr("suitewright.docs.state._cache", cache_store)
        cache_store.write("doc-abc123", sample_doc)

        requests_file = tmp_path / "requests.json"
        insert_req = [{"insertText": {"text": "x", "location": {"index": 1}}}]
        requests_file.write_text(json.dumps(insert_req))

        fresh_doc = {
            "documentId": "doc-abc123",
            "title": "Updated Title",
            "revisionId": "rev-after-update",
            "body": {"content": []},
        }
        mock_backoff.side_effect = [
            {"revisionId": "rev-xyz789"},  # staleness check
            {"documentId": "doc-abc123", "replies": []},  # batchUpdate
            fresh_doc,  # re-fetch
        ]

        args = SimpleNamespace(
            doc_id="doc-abc123", requests_file=str(requests_file), dry_run=False, compact=False
        )
        cmd_update(args)

        # Verify cache was refreshed with the new document
        loaded = cache_store.load("doc-abc123")
        assert loaded["title"] == "Updated Title"
        assert loaded["revisionId"] == "rev-after-update"


class TestRegisterUpdate:
    def test_register_includes_update_subcommand(self):
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        register(sub)

        choices = sub.choices
        assert "update" in choices

    def test_update_parser_has_required_arguments(self):
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        register(sub)

        args = parser.parse_args(["update", "my-doc-id", "/path/to/requests.json"])
        assert args.doc_id == "my-doc-id"
        assert args.requests_file == "/path/to/requests.json"
        assert args.dry_run is False
        assert hasattr(args, "func")

    def test_update_parser_accepts_dry_run_flag(self):
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        register(sub)

        args = parser.parse_args(["update", "my-doc-id", "req.json", "--dry-run"])
        assert args.dry_run is True
