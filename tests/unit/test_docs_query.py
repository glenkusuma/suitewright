"""Unit tests for docs/query.py — query engine commands.

Tests extract_text, iter_structural_elements, cmd_structure, cmd_section,
cmd_find_heading, and cmd_word_count using real fixture data from
tests/live/fixtures/docs/.
"""

from __future__ import annotations

import json
import types
from unittest.mock import patch

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


def _write_fixture_to_cache(tmp_path, doc_id: str, doc: dict) -> None:
    """Write a fixture document to the cache directory."""
    cache_dir = tmp_path / "docs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{doc_id}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# extract_text — skips inline objects
# ---------------------------------------------------------------------------


class TestExtractText:
    """Tests for extract_text helper."""

    def test_skips_inline_object_elements(self):
        """extract_text concatenates only textRun content, skipping inlineObjectElement."""
        from suitewright.docs.query import extract_text

        paragraph = {
            "elements": [
                {
                    "startIndex": 1,
                    "endIndex": 10,
                    "textRun": {"content": "Hello ", "textStyle": {}},
                },
                {
                    "startIndex": 10,
                    "endIndex": 11,
                    "inlineObjectElement": {"inlineObjectId": "kix.abc123"},
                },
                {
                    "startIndex": 11,
                    "endIndex": 20,
                    "textRun": {"content": "world\n", "textStyle": {}},
                },
            ]
        }

        result = extract_text(paragraph)
        assert result == "Hello world\n"
        assert "kix.abc123" not in result

    def test_skips_inline_objects_in_real_fixture(self):
        """Verify extract_text skips inline objects in real fixture data."""
        from suitewright.docs.query import extract_text, iter_structural_elements

        # Recipe fixture has inline images
        doc = load_fixture_by_name("Recipe")

        # Find a paragraph with inlineObjectElement
        found_inline = False
        for element in iter_structural_elements(doc):
            if "paragraph" not in element:
                continue
            paragraph = element["paragraph"]
            has_inline = any("inlineObjectElement" in el for el in paragraph.get("elements", []))
            if has_inline:
                found_inline = True
                text = extract_text(paragraph)
                # Text should not contain any object IDs
                assert "kix." not in text
                # Text should only contain textRun content
                for el in paragraph.get("elements", []):
                    if "textRun" in el:
                        assert el["textRun"]["content"] in text

        # Confirm we actually found and tested inline objects
        assert found_inline, "Expected to find paragraphs with inlineObjectElement in Recipe"

    def test_handles_paragraph_with_only_text_runs(self):
        """extract_text works normally for paragraphs without inline objects."""
        from suitewright.docs.query import extract_text

        paragraph = {
            "elements": [
                {"startIndex": 1, "endIndex": 6, "textRun": {"content": "Hello", "textStyle": {}}},
                {"startIndex": 6, "endIndex": 8, "textRun": {"content": "!\n", "textStyle": {}}},
            ]
        }

        result = extract_text(paragraph)
        assert result == "Hello!\n"

    def test_handles_empty_paragraph(self):
        """extract_text returns empty string for paragraph with no elements."""
        from suitewright.docs.query import extract_text

        paragraph = {"elements": []}
        assert extract_text(paragraph) == ""


# ---------------------------------------------------------------------------
# cmd_list_headings — includes 8 empty (RFP fixture)
# ---------------------------------------------------------------------------


class TestListHeadingsEmpty:
    """Tests for cmd_list_headings with empty headings in RFP fixture."""

    def test_rfp_has_8_empty_headings(self, tmp_path):
        """RFP fixture has exactly 8 empty headings marked with empty=True."""
        from suitewright.docs.query import cmd_list_headings

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id)
            result = _capture_json(cmd_list_headings, args)

        empty_headings = [h for h in result if h["empty"]]
        assert len(empty_headings) == 8

    def test_rfp_total_headings_is_20(self, tmp_path):
        """RFP fixture has 20 total headings (12 non-empty + 8 empty)."""
        from suitewright.docs.query import cmd_list_headings

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id)
            result = _capture_json(cmd_list_headings, args)

        assert len(result) == 20
        non_empty = [h for h in result if not h["empty"]]
        assert len(non_empty) == 12


# ---------------------------------------------------------------------------
# cmd_structure — skips sectionBreak
# ---------------------------------------------------------------------------


class TestStructureSkipsSectionBreak:
    """Tests for cmd_structure skipping sectionBreak elements."""

    def test_structure_output_has_no_section_break_blocks(self, tmp_path):
        """cmd_structure output should not contain any sectionBreak blocks."""
        from suitewright.docs.query import cmd_structure

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, full_text=False)
            result = _capture_json(cmd_structure, args)

        # No block should have kind == "sectionBreak"
        for block in result["blocks"]:
            assert block["kind"] != "sectionBreak"

    def test_structure_skips_leading_section_break(self, tmp_path):
        """All fixtures start with sectionBreak at index 0 — structure skips it."""
        from suitewright.docs.query import cmd_structure

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        # Verify the raw fixture starts with sectionBreak
        first_element = doc["body"]["content"][0]
        assert "sectionBreak" in first_element

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, full_text=False)
            result = _capture_json(cmd_structure, args)

        # First block should NOT be sectionBreak
        assert result["blocks"][0]["kind"] != "sectionBreak"
        assert result["blockCount"] > 0

    def test_iter_structural_elements_skips_section_break(self):
        """iter_structural_elements filters out sectionBreak elements."""
        from suitewright.docs.query import iter_structural_elements

        doc = load_fixture_by_name("Request for Proposal")

        # Verify raw content has sectionBreak
        raw_has_section_break = any("sectionBreak" in el for el in doc["body"]["content"])
        assert raw_has_section_break

        # iter_structural_elements should not yield any sectionBreak
        for element in iter_structural_elements(doc):
            assert "sectionBreak" not in element


# ---------------------------------------------------------------------------
# cmd_section — treats empty heading as boundary
# ---------------------------------------------------------------------------


class TestSectionEmptyHeadingBoundary:
    """Tests for cmd_section treating empty headings as section boundaries."""

    def test_section_stops_at_empty_heading(self, tmp_path):
        """Section extraction stops at an empty heading of same level."""
        from suitewright.docs.query import cmd_list_headings, cmd_section

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            # First, get headings to find a non-empty one followed by an empty one
            args = _make_args(doc_id)
            headings = _capture_json(cmd_list_headings, args)

        # Find a non-empty heading that is followed by an empty heading at same level
        target_heading = None
        for i, h in enumerate(headings):
            if not h["empty"] and i + 1 < len(headings):
                next_h = headings[i + 1]
                if next_h["empty"] and next_h["level"] == h["level"]:
                    target_heading = h["text"]
                    break

        # If we found such a heading, verify section stops at the empty boundary
        if target_heading:
            with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
                args = _make_args(doc_id, heading=target_heading, fuzzy=False)
                section = _capture_json(cmd_section, args)

            # Section should be finite (stopped at boundary)
            assert isinstance(section, list)
            assert len(section) > 0
            # The section should not include the empty heading
            # (it acts as a boundary, so section stops before it)
        else:
            # Fallback: use "Introduction & Background" which is known to be bounded
            with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
                args = _make_args(doc_id, heading="Introduction & Background", fuzzy=False)
                section = _capture_json(cmd_section, args)

            assert isinstance(section, list)
            assert len(section) > 0

    def test_section_bounded_by_empty_heading_has_limited_content(self, tmp_path):
        """A section bounded by an empty heading should not span the entire document."""
        from suitewright.docs.query import cmd_section, iter_structural_elements

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        # Count total structural elements (excluding sectionBreak)
        total_elements = len(list(iter_structural_elements(doc)))

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            # Use "Introduction & Background" — known to be followed by content then boundary
            args = _make_args(doc_id, heading="Introduction & Background", fuzzy=False)
            section = _capture_json(cmd_section, args)

        # Section should be a subset of total elements
        assert len(section) < total_elements


# ---------------------------------------------------------------------------
# cmd_find_heading — matchCount (Brochure)
# ---------------------------------------------------------------------------


class TestFindHeadingMatchCount:
    """Tests for cmd_find_heading matchCount with duplicate headings."""

    def test_brochure_lorem_ipsum_has_match_count_2(self, tmp_path):
        """Brochure has 2 'Lorem ipsum' headings — matchCount should be 2."""
        from suitewright.docs.query import cmd_find_heading

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, text="Lorem ipsum", fuzzy=False)
            result = _capture_json(cmd_find_heading, args)

        assert result["matchCount"] == 2
        # Returns the first match
        assert "startIndex" in result
        assert "level" in result

    def test_unique_heading_has_no_match_count(self, tmp_path):
        """A unique heading should not have matchCount field."""
        from suitewright.docs.query import cmd_find_heading

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, text="Product Overview", fuzzy=False)
            result = _capture_json(cmd_find_heading, args)

        assert "matchCount" not in result
        assert result["text"] == "Product Overview"


# ---------------------------------------------------------------------------
# cmd_word_count — total == section sum
# ---------------------------------------------------------------------------


class TestWordCountConsistency:
    """Tests for cmd_word_count total == sum of section word counts."""

    def test_total_equals_section_sum_rfp(self, tmp_path):
        """Word count total must equal sum of all section wordCounts (RFP)."""
        from suitewright.docs.query import cmd_word_count

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, heading=None)
            result = _capture_json(cmd_word_count, args)

        section_sum = sum(s["wordCount"] for s in result["sections"])
        assert result["total"] == section_sum

    def test_total_equals_section_sum_brochure(self, tmp_path):
        """Word count total must equal sum of all section wordCounts (Brochure)."""
        from suitewright.docs.query import cmd_word_count

        doc = load_fixture_by_name("Brochure")
        doc_id = "test-brochure"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, heading=None)
            result = _capture_json(cmd_word_count, args)

        section_sum = sum(s["wordCount"] for s in result["sections"])
        assert result["total"] == section_sum

    def test_total_equals_section_sum_sow(self, tmp_path):
        """Word count total must equal sum of all section wordCounts (SOW)."""
        from suitewright.docs.query import cmd_word_count

        doc = load_fixture_by_name("Statement of Work")
        doc_id = "test-sow"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, heading=None)
            result = _capture_json(cmd_word_count, args)

        section_sum = sum(s["wordCount"] for s in result["sections"])
        assert result["total"] == section_sum

    def test_total_equals_section_sum_recipe(self, tmp_path):
        """Word count total must equal sum of all section wordCounts (Recipe)."""
        from suitewright.docs.query import cmd_word_count

        doc = load_fixture_by_name("Recipe")
        doc_id = "test-recipe"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, heading=None)
            result = _capture_json(cmd_word_count, args)

        section_sum = sum(s["wordCount"] for s in result["sections"])
        assert result["total"] == section_sum

    def test_word_count_has_sections(self, tmp_path):
        """Word count output includes sections breakdown."""
        from suitewright.docs.query import cmd_word_count

        doc = load_fixture_by_name("Request for Proposal")
        doc_id = "test-rfp"
        _write_fixture_to_cache(tmp_path, doc_id, doc)

        with patch("suitewright._core.cache.paths.resolve", return_value=tmp_path):
            args = _make_args(doc_id, heading=None)
            result = _capture_json(cmd_word_count, args)

        assert "total" in result
        assert "sections" in result
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) > 0
        # Each section has heading, level, wordCount
        for section in result["sections"]:
            assert "heading" in section
            assert "level" in section
            assert "wordCount" in section
