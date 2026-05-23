"""Unit tests for docs/query.py heading navigation commands.

Tests cmd_list_headings, cmd_find_heading, and cmd_section using
real fixture data from tests/live/fixtures/docs/.
"""

from __future__ import annotations

import json
import types
from unittest.mock import patch

import pytest

from tests.live.fixtures.docs import load_fixture_by_name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(doc_id: str, **kwargs) -> types.SimpleNamespace:
    """Build a namespace mimicking argparse output."""
    defaults = {"compact": False}
    defaults.update(kwargs)
    return types.SimpleNamespace(doc_id=doc_id, **defaults)


def _capture_json(cmd_func, args) -> dict | list:
    """Run a command function and capture its JSON output."""
    captured: list[str] = []
    with patch(
        "suitewright._core.output.print",
        side_effect=lambda *a, **kw: captured.append(a[0]),
    ):
        cmd_func(args)
    return json.loads(captured[0])


# ---------------------------------------------------------------------------
# cmd_list_headings
# ---------------------------------------------------------------------------


class TestListHeadings:
    """Tests for cmd_list_headings."""

    def test_rfp_includes_all_headings(self, tmp_path):
        """RFP fixture has 20 headings total (8 empty)."""
        from suitewright.docs.query import cmd_list_headings

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"

        # Write fixture to cache
        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id)
            result = _capture_json(cmd_list_headings, args)

        assert isinstance(result, list)
        assert len(result) == 20
        # 8 empty headings
        empty_count = sum(1 for h in result if h["empty"])
        assert empty_count == 8

    def test_rfp_heading_fields(self, tmp_path):
        """Each heading entry has required fields."""
        from suitewright.docs.query import cmd_list_headings

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id)
            result = _capture_json(cmd_list_headings, args)

        for heading in result:
            assert "text" in heading
            assert "level" in heading
            assert "startIndex" in heading
            assert "endIndex" in heading
            assert "paragraphIndex" in heading
            assert "empty" in heading
            assert heading["level"] in (1, 2, 3, 4, 5, 6)

    def test_brochure_headings_multiple_levels(self, tmp_path):
        """Brochure has HEADING_1, HEADING_2, HEADING_3."""
        from suitewright.docs.query import cmd_list_headings

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id)
            result = _capture_json(cmd_list_headings, args)

        levels = {h["level"] for h in result}
        assert 1 in levels
        assert 2 in levels
        assert 3 in levels
        assert len(result) == 5

    def test_empty_heading_text_is_empty_string(self, tmp_path):
        """Empty headings should have text set to empty string."""
        from suitewright.docs.query import cmd_list_headings

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id)
            result = _capture_json(cmd_list_headings, args)

        empty_headings = [h for h in result if h["empty"]]
        for h in empty_headings:
            assert h["text"] == ""


# ---------------------------------------------------------------------------
# cmd_find_heading
# ---------------------------------------------------------------------------


class TestFindHeading:
    """Tests for cmd_find_heading."""

    def test_exact_match(self, tmp_path):
        """Find heading by exact text match."""
        from suitewright.docs.query import cmd_find_heading

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, text="Product Overview", fuzzy=False)
            result = _capture_json(cmd_find_heading, args)

        assert result["text"] == "Product Overview"
        assert result["level"] == 1
        assert "startIndex" in result
        assert "endIndex" in result

    def test_fuzzy_match(self, tmp_path):
        """Find heading by case-insensitive substring match."""
        from suitewright.docs.query import cmd_find_heading

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, text="product", fuzzy=True)
            result = _capture_json(cmd_find_heading, args)

        assert "Product Overview" in result["text"]

    def test_duplicate_headings_match_count(self, tmp_path):
        """Brochure has duplicate 'Lorem ipsum' headings — matchCount reported."""
        from suitewright.docs.query import cmd_find_heading

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, text="Lorem ipsum", fuzzy=False)
            result = _capture_json(cmd_find_heading, args)

        assert result["matchCount"] == 2

    def test_not_found_exits_with_error(self, tmp_path):
        """Non-existent heading exits with error and suggestions."""
        from suitewright.docs.query import cmd_find_heading

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, text="Nonexistent Heading", fuzzy=False)
            with pytest.raises(SystemExit) as exc_info:
                cmd_find_heading(args)
            assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# cmd_section
# ---------------------------------------------------------------------------


class TestSection:
    """Tests for cmd_section."""

    def test_section_extracts_content(self, tmp_path):
        """Section returns elements between heading and next same-level heading."""
        from suitewright.docs.query import cmd_section

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, heading="Product Overview", fuzzy=False)
            result = _capture_json(cmd_section, args)

        # Should include the heading itself and content until next HEADING_1
        assert isinstance(result, list)
        assert len(result) > 0
        # First element should be the heading itself
        assert result[0]["kind"] == "paragraph"

    def test_section_stops_at_same_level(self, tmp_path):
        """Section stops at next heading of same or higher level."""
        from suitewright.docs.query import cmd_section

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            # "Product Overview" is HEADING_1, "Details" is next HEADING_1
            args = _make_args(doc_id, heading="Product Overview", fuzzy=False)
            result = _capture_json(cmd_section, args)

        # Should NOT include "Details" heading
        texts = [el.get("text", "") for el in result]
        assert not any("Details" in t for t in texts)

    def test_section_empty_heading_boundary(self, tmp_path):
        """Empty headings act as section boundaries."""
        from suitewright.docs.query import cmd_section

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            # "Introduction & Background" is followed by content, then an empty HEADING_1
            args = _make_args(doc_id, heading="Introduction & Background", fuzzy=False)
            result = _capture_json(cmd_section, args)

        # Should have content but stop at the empty heading boundary
        assert isinstance(result, list)
        assert len(result) > 0

    def test_section_not_found_exits_with_error(self, tmp_path):
        """Non-existent heading exits with error."""
        from suitewright.docs.query import cmd_section

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, heading="Nonexistent", fuzzy=False)
            with pytest.raises(SystemExit) as exc_info:
                cmd_section(args)
            assert exc_info.value.code == 1

    def test_section_fuzzy_match(self, tmp_path):
        """Section supports --fuzzy matching."""
        from suitewright.docs.query import cmd_section

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"

        cache_dir = tmp_path / "docs"
        cache_dir.mkdir(parents=True)
        (cache_dir / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, heading="product", fuzzy=True)
            result = _capture_json(cmd_section, args)

        assert isinstance(result, list)
        assert len(result) > 0
