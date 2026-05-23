"""Tests for docs.tables pure helpers."""

from __future__ import annotations

import pytest

from suitewright.docs.mutate import (
    _cell_inner_range,
    _ensure_rectangular,
)
from suitewright.docs.tables import (
    _cell_text,
    _collect_tables,
    _table_summary,
)


def _make_para_cell(text: str, start: int, end: int) -> dict:
    return {
        "startIndex": start,
        "endIndex": end,
        "content": [
            {
                "startIndex": start + 1,
                "endIndex": end - 1,
                "paragraph": {"elements": [{"textRun": {"content": text}}]},
            }
        ],
    }


def _make_table_element(rows_data: list[list[str]], start: int = 10) -> dict:
    rows = []
    idx = start + 1
    for row_texts in rows_data:
        cells = []
        for text in row_texts:
            cell_start = idx
            cell_end = idx + len(text) + 4
            cells.append(_make_para_cell(text, cell_start, cell_end))
            idx = cell_end + 1
        rows.append({"tableCells": cells})
    return {
        "startIndex": start,
        "endIndex": idx,
        "table": {"tableRows": rows},
    }


class TestCollectTables:
    def test_finds_tables(self, sample_doc):
        tables = _collect_tables(sample_doc)
        assert len(tables) == 1
        _block_idx, element = tables[0]
        assert "table" in element

    def test_no_tables(self):
        doc = {
            "body": {
                "content": [
                    {
                        "startIndex": 1,
                        "endIndex": 10,
                        "paragraph": {"elements": [{"textRun": {"content": "text"}}]},
                    }
                ]
            }
        }
        assert _collect_tables(doc) == []

    def test_multiple_tables(self):
        t1 = _make_table_element([["A", "B"]], start=1)
        t2 = _make_table_element([["C", "D"]], start=50)
        doc = {"body": {"content": [t1, t2]}}
        tables = _collect_tables(doc)
        assert len(tables) == 2
        assert tables[0][0] == 0
        assert tables[1][0] == 1


class TestCellText:
    def test_extracts_text(self):
        cell = _make_para_cell("Hello", 10, 20)
        assert _cell_text(cell).strip() == "Hello"

    def test_empty_cell(self):
        cell = {"content": []}
        assert _cell_text(cell) == ""


class TestEnsureRectangular:
    def test_valid_table_passes(self, sample_table_element):
        _ensure_rectangular(sample_table_element["table"])  # should not raise

    def test_nested_table_raises(self):
        table = {
            "tableRows": [
                {
                    "tableCells": [
                        {
                            "content": [
                                {"table": {"tableRows": []}}  # nested table
                            ]
                        }
                    ]
                }
            ]
        }
        with pytest.raises(SystemExit, match="non-paragraph"):
            _ensure_rectangular(table)

    def test_empty_table_passes(self):
        _ensure_rectangular({"tableRows": []})


class TestTableSummary:
    def test_summary_shape(self, sample_table_element):
        summary = _table_summary(2, 0, sample_table_element)
        assert summary["tableIndex"] == 0
        assert summary["blockIndex"] == 2
        assert summary["rows"] == 2
        assert summary["cols"] == 3
        assert len(summary["cells"]) == 2
        assert summary["cells"][0] == ["Name", "Role", "Status"]
        assert summary["cells"][1] == ["Alice", "Owner", "Active"]


class TestCellInnerRange:
    def test_normal_cell(self):
        cell = {
            "startIndex": 10,
            "endIndex": 30,
            "content": [
                {
                    "startIndex": 11,
                    "endIndex": 25,
                    "paragraph": {"elements": [{"textRun": {"content": "text"}}]},
                }
            ],
        }
        start, end = _cell_inner_range(cell)
        assert start == 11
        assert end == 24  # endIndex - 1

    def test_empty_cell_content(self):
        cell = {"startIndex": 10, "endIndex": 20, "content": []}
        start, end = _cell_inner_range(cell)
        assert start == end  # no range to delete

    def test_no_paragraphs(self):
        cell = {
            "startIndex": 10,
            "endIndex": 20,
            "content": [{"table": {}}],  # non-paragraph
        }
        start, end = _cell_inner_range(cell)
        assert start == end
