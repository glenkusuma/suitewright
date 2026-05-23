"""Live mutate tests for the docs cache-first workflow.

Tests the new grouped CLI commands:
- docs mutate append (with cache refresh)
- docs mutate replace-all (with cache refresh)
- docs cache update (guarded batchUpdate via requests file)
- --dry-run mode (no actual mutation)

Run with:
    uv run pytest tests/live/mutate/test_docs_cache_mutate.py --run-live -v

Must complete in <120s total.
"""

from __future__ import annotations

import json

import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]


@pytest.fixture(scope="module")
def mutate_doc(sandbox):
    """Create a document for cache-first mutate tests.

    Contains searchable markers for replace-all and append verification.
    """
    title = sandbox.name("docs-cache-mutate")
    body = (
        "Cache Mutate Test Document\n"
        "First paragraph with REPLACE_TARGET marker.\n"
        "Second paragraph also has REPLACE_TARGET here.\n"
        "Final paragraph for append testing.\n"
    )
    created = cli_run(["docs", "create", "--title", title, "--body", body])
    doc_id = created["documentId"]
    sandbox.track("drive", doc_id)

    # Move into sandbox folder
    from suitewright._core.service import build_service

    drive = build_service("drive", "v3")
    drive.files().update(
        fileId=doc_id,
        addParents=sandbox.folder_id,
        removeParents="root",
        fields="id, parents",
    ).execute()

    # Fetch into cache for subsequent tests
    cli_run(["docs", "cache", "fetch", doc_id])

    return doc_id


class TestMutateAppend:
    """docs mutate append — appends text and refreshes cache."""

    def test_append_text_and_cache_refreshed(self, sandbox, mutate_doc):
        marker = "APPENDED_CACHE_MARKER"
        result = cli_run(["docs", "mutate", "append", mutate_doc, "--text", marker])
        assert result["status"] == "appended"

        # Verify cache was auto-refreshed: query get should find the marker
        text = cli_run(["docs", "query", "get", mutate_doc], expect_json=False)
        assert marker in text


class TestMutateReplaceAll:
    """docs mutate replace-all — find/replace with cache refresh."""

    def test_replace_all_changes_occurrences(self, sandbox, mutate_doc):
        result = cli_run(
            [
                "docs",
                "mutate",
                "replace-all",
                mutate_doc,
                "--find",
                "REPLACE_TARGET",
                "--replace",
                "REPLACED_VALUE",
            ]
        )
        assert result["status"] == "replaced"

        # Verify via query that replacements took effect
        text = cli_run(["docs", "query", "get", mutate_doc], expect_json=False)
        assert "REPLACE_TARGET" not in text
        assert "REPLACED_VALUE" in text


class TestCacheUpdateWithRequestsFile:
    """docs cache update — guarded batchUpdate via requests file."""

    def test_update_with_requests_file(self, sandbox, mutate_doc, tmp_path):
        # Ensure cache is fresh
        cli_run(["docs", "cache", "fetch", mutate_doc])

        # Build a requests file that inserts text
        requests = [{"insertText": {"location": {"index": 1}, "text": "REQUESTS_FILE_MARKER\n"}}]
        requests_file = tmp_path / "update_requests.json"
        requests_file.write_text(json.dumps(requests))

        result = cli_run(["docs", "cache", "update", mutate_doc, str(requests_file)])
        assert result["status"] == "updated"
        assert result["documentId"] == mutate_doc

        # Verify the text was inserted and cache refreshed
        text = cli_run(["docs", "query", "get", mutate_doc], expect_json=False)
        assert "REQUESTS_FILE_MARKER" in text


class TestDryRun:
    """--dry-run mode — no actual mutation occurs."""

    def test_mutate_append_dry_run(self, sandbox, mutate_doc):
        # Ensure cache is fresh
        cli_run(["docs", "cache", "fetch", mutate_doc])

        result = cli_run(
            [
                "docs",
                "mutate",
                "append",
                mutate_doc,
                "--text",
                "DRY_RUN_SHOULD_NOT_APPEAR",
                "--dry-run",
            ]
        )
        assert result["status"] == "dry-run"
        assert result["requestCount"] >= 1

        # Verify no change occurred — re-fetch and check
        cli_run(["docs", "cache", "fetch", mutate_doc])
        text_after = cli_run(["docs", "query", "get", mutate_doc], expect_json=False)
        assert "DRY_RUN_SHOULD_NOT_APPEAR" not in text_after

    def test_cache_update_dry_run(self, sandbox, mutate_doc, tmp_path):
        # Ensure cache is fresh
        cli_run(["docs", "cache", "fetch", mutate_doc])

        requests = [{"insertText": {"location": {"index": 1}, "text": "DRY_RUN_UPDATE_MARKER\n"}}]
        requests_file = tmp_path / "dry_run_requests.json"
        requests_file.write_text(json.dumps(requests))

        result = cli_run(
            [
                "docs",
                "cache",
                "update",
                mutate_doc,
                str(requests_file),
                "--dry-run",
            ]
        )
        assert result["status"] == "dry-run"
        assert result["requestCount"] >= 1

        # Verify no change occurred
        cli_run(["docs", "cache", "fetch", mutate_doc])
        text_after = cli_run(["docs", "query", "get", mutate_doc], expect_json=False)
        assert "DRY_RUN_UPDATE_MARKER" not in text_after
