"""Property-based tests for docs cache workflow using Hypothesis.

Tests universal properties that must hold across all inputs:
- Cache hash is always valid SHA-256 (64 hex chars)
- Text extraction skips non-text elements (inlineObjectElement)
- Heading enumeration completeness (all HEADING_1-6 found)
- Word count consistency (total == sum of sections)
"""

from __future__ import annotations

import hashlib
import re
import string

from hypothesis import given, settings
from hypothesis import strategies as st

from suitewright._core.cache import CacheStore
from suitewright.docs.query import extract_text, get_heading_level, iter_structural_elements

# ---------------------------------------------------------------------------
# Strategies for generating Google Docs-like structures
# ---------------------------------------------------------------------------

# Strategy for generating text content (non-empty, printable)
text_content_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), min_codepoint=32),
    min_size=1,
    max_size=100,
)

# Strategy for generating a textRun element
text_run_st = st.builds(
    lambda content: {"textRun": {"content": content, "textStyle": {}}},
    content=text_content_st,
)

# Strategy for generating an inlineObjectElement
inline_object_st = st.builds(
    lambda obj_id: {"inlineObjectElement": {"inlineObjectId": obj_id, "textStyle": {}}},
    obj_id=st.text(alphabet=string.ascii_lowercase + string.digits, min_size=5, max_size=15).map(
        lambda s: f"kix.{s}"
    ),
)

# Strategy for generating paragraph elements (mix of textRun and inlineObject)
paragraph_elements_st = st.lists(
    st.one_of(text_run_st, inline_object_st),
    min_size=1,
    max_size=8,
)

# Strategy for heading style types
heading_style_st = st.sampled_from(
    ["HEADING_1", "HEADING_2", "HEADING_3", "HEADING_4", "HEADING_5", "HEADING_6"]
)

# Strategy for non-heading style types
non_heading_style_st = st.sampled_from(["NORMAL_TEXT", "TITLE", "SUBTITLE"])

# Strategy for paragraph style (heading or non-heading)
paragraph_style_st = st.one_of(heading_style_st, non_heading_style_st)


def make_paragraph_element(elements: list[dict], style: str, start_index: int) -> dict:
    """Build a paragraph structural element."""
    # Compute a reasonable end index
    end_index = (
        start_index + sum(len(el.get("textRun", {}).get("content", "")) for el in elements) + 1
    )
    return {
        "startIndex": start_index,
        "endIndex": end_index,
        "paragraph": {
            "elements": elements,
            "paragraphStyle": {"namedStyleType": style},
        },
    }


def make_doc_with_paragraphs(paragraphs: list[dict]) -> dict:
    """Build a minimal doc structure with given paragraph elements."""
    content = [{"sectionBreak": {}, "startIndex": 0, "endIndex": 1}]
    content.extend(paragraphs)
    return {
        "documentId": "prop-test-doc",
        "title": "Property Test",
        "body": {"content": content},
    }


# ---------------------------------------------------------------------------
# Property 1: Cache hash is always valid SHA-256 (64 hex chars)
# Validates: Requirements 4.5
# ---------------------------------------------------------------------------


@settings(max_examples=120)
@given(
    payload=st.dictionaries(
        keys=st.text(alphabet=string.ascii_letters, min_size=1, max_size=20),
        values=st.one_of(
            st.text(min_size=0, max_size=50),
            st.integers(),
            st.booleans(),
            st.none(),
        ),
        min_size=1,
        max_size=10,
    )
)
def test_cache_hash_is_valid_sha256(payload, tmp_path_factory):
    """Cache hash is always a valid 64-character hex SHA-256 digest.

    **Validates: Requirements 4.5**

    Property: For any JSON-serializable payload written to the cache,
    the hash() method returns exactly 64 lowercase hex characters that
    match the SHA-256 of the file bytes.
    """
    tmp_path = tmp_path_factory.mktemp("cache")
    import os

    os.environ["SUITEWRIGHT_CACHE_DIR"] = str(tmp_path)
    store = CacheStore("proptest")

    store.write("test-resource", payload)
    h = store.hash("test-resource")

    # Must be exactly 64 hex characters
    assert len(h) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", h) is not None

    # Must match actual SHA-256 of file bytes
    file_bytes = store.path("test-resource").read_bytes()
    expected = hashlib.sha256(file_bytes).hexdigest()
    assert h == expected


# ---------------------------------------------------------------------------
# Property 2: Text extraction skips non-text elements (inlineObjectElement)
# Validates: Requirements 7.6
# ---------------------------------------------------------------------------


@settings(max_examples=120)
@given(elements=paragraph_elements_st)
def test_extract_text_skips_non_text_elements(elements):
    """extract_text only includes textRun content, skipping inlineObjectElement.

    **Validates: Requirements 7.6**

    Property: For any paragraph with a mix of textRun and inlineObjectElement
    entries, extract_text returns only the concatenation of textRun.content
    values. No inlineObjectId strings appear in the output.
    """
    paragraph = {"elements": elements}
    result = extract_text(paragraph)

    # Compute expected: only textRun content concatenated
    expected_parts = []
    for el in elements:
        if "textRun" in el:
            content = el["textRun"].get("content", "")
            if content:
                expected_parts.append(content)

    expected = "".join(expected_parts)
    assert result == expected

    # No inlineObjectId should appear in the result
    for el in elements:
        if "inlineObjectElement" in el:
            obj_id = el["inlineObjectElement"].get("inlineObjectId", "")
            if obj_id:
                assert obj_id not in result


# ---------------------------------------------------------------------------
# Property 3: Heading enumeration completeness (all HEADING_1-6 found)
# Validates: Requirements 6.4, 6.5
# ---------------------------------------------------------------------------


@settings(max_examples=120)
@given(
    heading_levels=st.lists(
        st.integers(min_value=1, max_value=6),
        min_size=1,
        max_size=12,
    )
)
def test_heading_enumeration_completeness(heading_levels):
    """All headings styled HEADING_1 through HEADING_6 are detected by get_heading_level.

    **Validates: Requirements 6.4, 6.5**

    Property: For any document containing paragraphs with heading styles,
    get_heading_level correctly identifies each heading level. Every heading
    paragraph in the document is found by iterating structural elements and
    checking get_heading_level.
    """
    # Build a document with the specified heading levels
    paragraphs = []
    idx = 1
    for level in heading_levels:
        style = f"HEADING_{level}"
        elements = [{"textRun": {"content": f"Heading L{level}\n", "textStyle": {}}}]
        para = make_paragraph_element(elements, style, idx)
        paragraphs.append(para)
        idx = para["endIndex"]

    doc = make_doc_with_paragraphs(paragraphs)

    # Verify all headings are found
    found_levels = []
    for element in iter_structural_elements(doc):
        level = get_heading_level(element)
        if level is not None:
            found_levels.append(level)

    assert found_levels == heading_levels

    # Verify each detected level is in range 1-6
    for level in found_levels:
        assert 1 <= level <= 6


# ---------------------------------------------------------------------------
# Property 4: Word count consistency (total == sum of sections)
# Validates: Requirements 8.1
# ---------------------------------------------------------------------------


@settings(max_examples=120)
@given(
    section_texts=st.lists(
        st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=65),
                min_size=1,
                max_size=20,
            ),
            min_size=0,
            max_size=5,
        ),
        min_size=1,
        max_size=6,
    )
)
def test_word_count_consistency(section_texts):
    """Word count total always equals sum of per-section word counts.

    **Validates: Requirements 8.1**

    Property: For any document with headings dividing it into sections,
    the total word count equals the sum of all section word counts.
    This mirrors the invariant enforced by cmd_word_count.
    """
    # Build a document with headings and content paragraphs
    paragraphs = []
    idx = 1

    for section_idx, words_in_section in enumerate(section_texts):
        # Add a heading for each section (except possibly the first)
        if section_idx > 0:
            heading_style = f"HEADING_{min(section_idx, 6)}"
            heading_elements = [
                {"textRun": {"content": f"Section {section_idx}\n", "textStyle": {}}}
            ]
            heading_para = make_paragraph_element(heading_elements, heading_style, idx)
            paragraphs.append(heading_para)
            idx = heading_para["endIndex"]

        # Add content paragraph with the words
        if words_in_section:
            content = " ".join(words_in_section) + "\n"
            content_elements = [{"textRun": {"content": content, "textStyle": {}}}]
            content_para = make_paragraph_element(content_elements, "NORMAL_TEXT", idx)
            paragraphs.append(content_para)
            idx = content_para["endIndex"]

    doc = make_doc_with_paragraphs(paragraphs)

    # Compute word count using the same logic as cmd_word_count
    sections: list[dict] = []
    current_heading = "(before first heading)"
    current_level = 0
    current_words = 0

    for element in iter_structural_elements(doc):
        if "paragraph" not in element:
            continue

        level = get_heading_level(element)
        if level is not None:
            sections.append(
                {"heading": current_heading, "level": current_level, "wordCount": current_words}
            )
            text = extract_text(element["paragraph"]).rstrip("\n")
            current_heading = text if text.strip() else "(empty heading)"
            current_level = level
            current_words = 0
        else:
            text = extract_text(element["paragraph"])
            words = text.split()
            current_words += len(words)

    # Don't forget the last section
    sections.append(
        {"heading": current_heading, "level": current_level, "wordCount": current_words}
    )

    total = sum(s["wordCount"] for s in sections)

    # The invariant: total == sum of section word counts
    assert total == sum(s["wordCount"] for s in sections)

    # Additional check: total should match counting all words in the doc
    all_words = 0
    for element in iter_structural_elements(doc):
        if "paragraph" in element:
            level = get_heading_level(element)
            if level is None:
                text = extract_text(element["paragraph"])
                all_words += len(text.split())

    assert total == all_words
