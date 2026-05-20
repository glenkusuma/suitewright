"""Tests for suitewright.render pure functions."""

from __future__ import annotations

from suitewright import render


def _para(text: str) -> dict:
    return {"paragraph": {"elements": [{"textRun": {"content": text}}]}}


def _para_elem(text: str, start: int = 1, end: int = 10) -> dict:
    return {
        "startIndex": start,
        "endIndex": end,
        "paragraph": {"elements": [{"textRun": {"content": text}}]},
    }


class TestParagraphText:
    def test_single_run(self):
        para = {"elements": [{"textRun": {"content": "Hello"}}]}
        assert render.paragraph_text(para) == "Hello"

    def test_multiple_runs(self):
        para = {
            "elements": [
                {"textRun": {"content": "Hello, "}},
                {"textRun": {"content": "world!"}},
            ]
        }
        assert render.paragraph_text(para) == "Hello, world!"

    def test_empty_elements(self):
        assert render.paragraph_text({"elements": []}) == ""

    def test_missing_content_skipped(self):
        para = {"elements": [{"textRun": {}}, {"textRun": {"content": "ok"}}]}
        assert render.paragraph_text(para) == "ok"

    def test_no_text_run(self):
        para = {"elements": [{"inlineObjectElement": {}}]}
        assert render.paragraph_text(para) == ""


class TestTableText:
    def test_basic_table(self, sample_table_element):
        text = render.table_text(sample_table_element["table"])
        assert "Name" in text
        assert "Role" in text
        assert "Alice" in text
        lines = text.split("\n")
        assert len(lines) == 2

    def test_empty_table(self):
        assert render.table_text({"tableRows": []}) == ""


class TestStructuralElementsText:
    def test_paragraphs_joined_by_newline(self):
        elements = [_para("Line 1\n"), _para("Line 2\n")]
        result = render.structural_elements_text(elements)
        assert "Line 1" in result
        assert "Line 2" in result

    def test_custom_joiner(self):
        elements = [_para("A"), _para("B")]
        result = render.structural_elements_text(elements, joiner=" | ")
        assert " | " in result

    def test_empty_paragraphs_skipped(self):
        elements = [_para(""), _para("Real content")]
        result = render.structural_elements_text(elements)
        assert result == "Real content"

    def test_table_of_contents(self):
        elements = [{"tableOfContents": {"content": [_para("Chapter 1"), _para("Chapter 2")]}}]
        result = render.structural_elements_text(elements)
        assert "Chapter 1" in result

    def test_empty_list(self):
        assert render.structural_elements_text([]) == ""


class TestCompactPreview:
    def test_short_text_unchanged(self):
        assert render.compact_preview("Hello") == "Hello"

    def test_long_text_truncated(self):
        text = "A" * 200
        result = render.compact_preview(text)
        assert len(result) <= 103
        assert result.endswith("...")

    def test_whitespace_collapsed(self):
        result = render.compact_preview("  hello   world  ")
        assert result == "hello world"

    def test_custom_limit(self):
        text = "A" * 50
        result = render.compact_preview(text, limit=20)
        assert len(result) <= 23
        assert result.endswith("...")

    def test_exactly_at_limit(self):
        text = "A" * 100
        result = render.compact_preview(text, limit=100)
        assert result == text
        assert not result.endswith("...")


class TestShowStructureBlock:
    def test_paragraph_preview(self, sample_paragraph_element):
        block = render.show_structure_block(sample_paragraph_element, 0, full_text=False)
        assert block is not None
        assert block["kind"] == "paragraph"
        assert "preview" in block
        assert "text" not in block
        assert block["index"] == 0

    def test_paragraph_full_text(self, sample_paragraph_element):
        block = render.show_structure_block(sample_paragraph_element, 0, full_text=True)
        assert "text" in block
        assert "preview" not in block

    def test_table_block(self, sample_table_element):
        block = render.show_structure_block(sample_table_element, 1, full_text=False)
        assert block is not None
        assert block["kind"] == "table"
        assert block["rows"] == 2
        assert block["cols"] == 3

    def test_table_full_text(self, sample_table_element):
        block = render.show_structure_block(sample_table_element, 1, full_text=True)
        assert "text" in block

    def test_unknown_element_returns_none(self):
        element = {"startIndex": 1, "endIndex": 2, "sectionBreak": {}}
        assert render.show_structure_block(element, 0, full_text=False) is None

    def test_toc_block(self):
        element = {
            "startIndex": 5,
            "endIndex": 20,
            "tableOfContents": {"content": [_para("Intro"), _para("Chapter 1")]},
        }
        block = render.show_structure_block(element, 0, full_text=False)
        assert block is not None
        assert block["kind"] == "tableOfContents"
        assert "preview" in block


class TestDocumentEndIndex:
    def test_normal_doc(self, sample_doc):
        idx = render.document_end_index(sample_doc)
        assert idx == 121

    def test_empty_content(self):
        doc = {"body": {"content": []}}
        assert render.document_end_index(doc) == 1

    def test_missing_body(self):
        assert render.document_end_index({}) == 1
