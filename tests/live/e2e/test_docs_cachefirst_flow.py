"""E2E tests for the docs cache-first workflow — full loop with 2 documents.

Per Requirement 16.6: one "bad state" doc for the fix workflow, and one
"good state" doc for query accuracy validation against known content.

Bad state doc flow:
    create → fetch → validate → find-text → dry-run → replace-all →
    verify → validate revision changed

Good state doc flow:
    create with known content → fetch → query accuracy validation
    (structure, get, word-count, list-headings match expected)

Run with:
    uv run pytest tests/live/e2e/test_docs_cachefirst_flow.py --run-live -v -k docs_cachefirst

Must complete in <120s total.
"""

from __future__ import annotations

import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bad_state_doc(sandbox):
    """Create a document with intentional bad state for the fix workflow.

    Contains:
    - A typo (TPYO_MARKER) to detect and fix via replace-all
    - Multiple heading levels for structural validation
    - Searchable content for find-text verification
    """
    title = sandbox.name("docs-e2e-bad-state")
    body = (
        "Introduction\n"
        "This document has a TPYO_MARKER that needs fixing.\n"
        "Background\n"
        "The background section provides context. Another TPYO_MARKER here.\n"
        "Methodology\n"
        "We use a cache-first approach for all operations.\n"
        "Results\n"
        "The results show improvement after corrections.\n"
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


@pytest.fixture(scope="module")
def good_state_doc(sandbox):
    """Create a document with known content for query accuracy validation.

    Contains:
    - Exactly 3 heading-like lines (will be plain paragraphs in the doc)
    - Known word counts per section
    - Predictable structure for validation
    """
    title = sandbox.name("docs-e2e-good-state")
    body = (
        "Project Overview\n"
        "This is the overview section with exactly ten words in this line.\n"
        "Technical Details\n"
        "The technical section covers implementation specifics and design choices.\n"
        "Conclusion\n"
        "Final summary wrapping up the document content here.\n"
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
# Bad State Document — Fix Workflow
# ---------------------------------------------------------------------------


class TestBadStateFixWorkflow:
    """Full cache-first fix loop: create → fetch → validate → find → fix → verify."""

    def test_fetch_and_validate(self, sandbox, bad_state_doc):
        """Step 1-2: Fetch into cache and validate freshness."""
        result = cli_run(["docs", "cache", "fetch", bad_state_doc])
        assert result["status"] == "cached"
        assert "revisionId" in result

        validate = cli_run(["docs", "cache", "validate", bad_state_doc])
        assert validate["status"] == "ok"
        assert validate["revisionId"] is not None

    def test_find_text_detects_typo(self, sandbox, bad_state_doc):
        """Step 3: Use find-text to detect the typo marker."""
        cli_run(["docs", "cache", "fetch", bad_state_doc])
        result = cli_run(
            [
                "docs",
                "query",
                "find-text",
                bad_state_doc,
                "--pattern",
                "TPYO_MARKER",
            ]
        )
        # find-text returns a bare list of matches
        assert isinstance(result, list)
        assert len(result) >= 2, "Should find TPYO_MARKER in at least 2 paragraphs"

    def test_dry_run_does_not_mutate(self, sandbox, bad_state_doc):
        """Step 4: Dry-run replace-all confirms no changes applied."""
        cli_run(["docs", "cache", "fetch", bad_state_doc])

        result = cli_run(
            [
                "docs",
                "mutate",
                "replace-all",
                bad_state_doc,
                "--find",
                "TPYO_MARKER",
                "--replace",
                "FIXED_MARKER",
                "--dry-run",
            ]
        )
        assert result["status"] == "dry-run"

        # Verify typo still present
        find_result = cli_run(
            [
                "docs",
                "query",
                "find-text",
                bad_state_doc,
                "--pattern",
                "TPYO_MARKER",
            ]
        )
        assert len(find_result) >= 2

    def test_replace_all_fixes_typo(self, sandbox, bad_state_doc):
        """Step 5: Replace-all fixes the typo and cache auto-refreshes."""
        cli_run(["docs", "cache", "fetch", bad_state_doc])

        # Capture revision before mutation
        validate_before = cli_run(["docs", "cache", "validate", bad_state_doc])
        revision_before = validate_before["revisionId"]

        # Execute the fix
        result = cli_run(
            [
                "docs",
                "mutate",
                "replace-all",
                bad_state_doc,
                "--find",
                "TPYO_MARKER",
                "--replace",
                "FIXED_MARKER",
            ]
        )
        assert result["status"] == "replaced"

        # Step 6: Verify fix applied via query (cache was auto-refreshed)
        text = cli_run(["docs", "query", "get", bad_state_doc], expect_json=False)
        assert "TPYO_MARKER" not in text
        assert "FIXED_MARKER" in text

        # Step 7: Validate revision changed after mutation
        validate_after = cli_run(["docs", "cache", "validate", bad_state_doc])
        assert validate_after["status"] == "ok"
        assert validate_after["revisionId"] != revision_before


# ---------------------------------------------------------------------------
# Good State Document — Query Accuracy Validation
# ---------------------------------------------------------------------------


class TestGoodStateQueryAccuracy:
    """Validate query commands return accurate results against known content."""

    def test_fetch_good_state(self, sandbox, good_state_doc):
        """Fetch the good state doc into cache."""
        result = cli_run(["docs", "cache", "fetch", good_state_doc])
        assert result["status"] == "cached"

    def test_query_structure_returns_blocks(self, sandbox, good_state_doc):
        """Structure command returns paragraph blocks matching known content."""
        cli_run(["docs", "cache", "fetch", good_state_doc])
        result = cli_run(["docs", "query", "structure", good_state_doc])
        assert "blocks" in result
        assert isinstance(result["blocks"], list)
        # We inserted 6 lines of text — should have at least 6 paragraph blocks
        paragraph_blocks = [b for b in result["blocks"] if b["kind"] == "paragraph"]
        assert len(paragraph_blocks) >= 6

    def test_query_get_returns_full_text(self, sandbox, good_state_doc):
        """Get command returns all known content as plain text."""
        cli_run(["docs", "cache", "fetch", good_state_doc])
        text = cli_run(["docs", "query", "get", good_state_doc], expect_json=False)
        assert "Project Overview" in text
        assert "Technical Details" in text
        assert "Conclusion" in text
        assert "implementation specifics" in text
        assert "Final summary" in text

    def test_query_word_count_positive(self, sandbox, good_state_doc):
        """Word count returns a positive total matching the known content."""
        cli_run(["docs", "cache", "fetch", good_state_doc])
        result = cli_run(["docs", "query", "word-count", good_state_doc])
        assert "total" in result
        assert isinstance(result["total"], int)
        # Our known content has roughly 30-40 words
        assert result["total"] >= 25
        assert result["total"] <= 100

    def test_query_list_headings(self, sandbox, good_state_doc):
        """List-headings returns a list (may be empty if doc uses plain text)."""
        cli_run(["docs", "cache", "fetch", good_state_doc])
        result = cli_run(["docs", "query", "list-headings", good_state_doc])
        # list-headings returns a bare JSON array
        assert isinstance(result, list)
        # Note: headings may be empty since docs created via --body use NORMAL_TEXT style.
        # This validates the command runs correctly against the cached doc.
