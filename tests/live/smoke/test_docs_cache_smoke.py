"""Smoke tests for the docs cache-first workflow CLI commands.

Read-only tests against the live Google Docs API. Creates a simple test document
at session start, then validates each cache and query subcommand returns the
expected JSON shape and exit code.

Run with:
    uv run pytest tests/live/smoke/test_docs_cache_smoke.py --run-live -v

Must complete in <60s total.
"""

from __future__ import annotations

import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.smoke]


@pytest.fixture(scope="module")
def smoke_doc(sandbox):
    """Create a minimal test document for read-only smoke tests.

    The document contains:
    - A HEADING_1 paragraph
    - Body text with a searchable marker
    - A second heading for section/word-count testing
    - Additional body text
    """
    title = sandbox.name("docs-cache-smoke")
    body = (
        "Smoke Test Heading\n"
        "This is the first paragraph with a SMOKE_MARKER token.\n"
        "Second Heading\n"
        "Content under the second heading for word count verification.\n"
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

    return doc_id


# ---------------------------------------------------------------------------
# Cache subcommands
# ---------------------------------------------------------------------------


class TestCacheFetch:
    """docs cache fetch — pull live doc into local JSON cache."""

    def test_returns_status_cached(self, sandbox, smoke_doc):
        result = cli_run(["docs", "cache", "fetch", smoke_doc])
        assert result["status"] == "cached"
        assert result["documentId"] == smoke_doc
        assert "cachePath" in result
        assert "title" in result

    def test_includes_revision_id(self, sandbox, smoke_doc):
        """Confirms edit-access credentials return revisionId."""
        result = cli_run(["docs", "cache", "fetch", smoke_doc])
        assert "revisionId" in result, "revisionId should be present when fetching with edit access"
        assert isinstance(result["revisionId"], str)
        assert len(result["revisionId"]) > 0


class TestCacheShow:
    """docs cache show — print cache file path + metadata."""

    def test_returns_path(self, sandbox, smoke_doc):
        # Ensure cache exists
        cli_run(["docs", "cache", "fetch", smoke_doc])
        result = cli_run(["docs", "cache", "show", smoke_doc])
        assert "cachePath" in result
        assert smoke_doc in result["cachePath"]

    def test_missing_cache_errors(self, sandbox):
        """Requesting show for a non-existent doc ID should error."""
        proc = cli_run(
            ["docs", "cache", "show", "nonexistent-doc-id-12345"],
            allow_nonzero=True,
            expect_json=False,
        )
        assert proc.returncode != 0


class TestCacheValidate:
    """docs cache validate — check cache freshness."""

    def test_returns_status_ok(self, sandbox, smoke_doc):
        # Ensure cache is fresh
        cli_run(["docs", "cache", "fetch", smoke_doc])
        result = cli_run(["docs", "cache", "validate", smoke_doc])
        assert result["status"] == "ok"
        assert result["documentId"] == smoke_doc
        assert "cacheHash" in result
        assert "revisionId" in result
        assert "cachePath" in result


# ---------------------------------------------------------------------------
# Query subcommands
# ---------------------------------------------------------------------------


class TestQueryStructure:
    """docs query structure — show structural outline."""

    def test_returns_blocks(self, sandbox, smoke_doc):
        cli_run(["docs", "cache", "fetch", smoke_doc])
        result = cli_run(["docs", "query", "structure", smoke_doc])
        assert "blocks" in result
        assert isinstance(result["blocks"], list)
        assert len(result["blocks"]) > 0

    def test_no_section_break_first(self, sandbox, smoke_doc):
        """The first block should NOT be a sectionBreak (they are skipped)."""
        cli_run(["docs", "cache", "fetch", smoke_doc])
        result = cli_run(["docs", "query", "structure", smoke_doc])
        first_block = result["blocks"][0]
        assert first_block["kind"] != "sectionBreak"


class TestQueryGet:
    """docs query get — plain text extraction."""

    def test_returns_text(self, sandbox, smoke_doc):
        cli_run(["docs", "cache", "fetch", smoke_doc])
        # query get returns plain text, not JSON
        text = cli_run(["docs", "query", "get", smoke_doc], expect_json=False)
        assert isinstance(text, str)
        assert len(text) > 0
        assert "SMOKE_MARKER" in text


class TestQueryListHeadings:
    """docs query list-headings — list all headings with levels."""

    def test_returns_headings_array(self, sandbox, smoke_doc):
        cli_run(["docs", "cache", "fetch", smoke_doc])
        result = cli_run(["docs", "query", "list-headings", smoke_doc])
        # list-headings returns a bare JSON array
        assert isinstance(result, list)


class TestQueryFindText:
    """docs query find-text — regex search in paragraphs."""

    def test_finds_marker(self, sandbox, smoke_doc):
        cli_run(["docs", "cache", "fetch", smoke_doc])
        result = cli_run(["docs", "query", "find-text", smoke_doc, "--pattern", "SMOKE_MARKER"])
        # find-text returns a bare JSON array of matches
        assert isinstance(result, list)
        assert len(result) > 0

    def test_no_match_returns_empty(self, sandbox, smoke_doc):
        cli_run(["docs", "cache", "fetch", smoke_doc])
        result = cli_run(
            ["docs", "query", "find-text", smoke_doc, "--pattern", "NONEXISTENT_xyz_999"]
        )
        # find-text returns a bare JSON array (empty when no matches)
        assert isinstance(result, list)
        assert len(result) == 0


class TestQueryWordCount:
    """docs query word-count — word count total + per-section."""

    def test_returns_total(self, sandbox, smoke_doc):
        cli_run(["docs", "cache", "fetch", smoke_doc])
        result = cli_run(["docs", "query", "word-count", smoke_doc])
        assert "total" in result
        assert isinstance(result["total"], int)
        assert result["total"] > 0
