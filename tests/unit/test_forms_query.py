"""Tests for forms.query pure helpers."""

from __future__ import annotations

import json
import types

import pytest

from suitewright.forms.query import (
    DEFAULT_LABEL_PATTERN,
    cmd_indexer,
    compact_item,
    find_index_by_item_id,
    find_index_by_title,
    top_level_items,
)


class TestTopLevelItems:
    def test_returns_items(self, sample_form):
        items = top_level_items(sample_form)
        assert len(items) == 3

    def test_empty_form(self):
        assert top_level_items({}) == []


class TestCompactItem:
    def test_question_item(self, sample_form):
        item = sample_form["items"][0]
        result = compact_item(item, 0)
        assert result["index"] == 0
        assert result["itemId"] == "item001"
        assert result["title"] == "A1. First question"
        assert result["kind"] == "questionItem"
        assert result["questionId"] == "q001"
        assert result["required"] is True
        assert result["questionType"] == "text"

    def test_choice_question(self, sample_form):
        item = sample_form["items"][1]
        result = compact_item(item, 1)
        assert result["kind"] == "questionItem"
        assert result["questionType"] == "RADIO"
        assert len(result["options"]) == 2

    def test_text_item(self, sample_form):
        item = sample_form["items"][2]
        result = compact_item(item, 2)
        assert result["kind"] == "textItem"

    def test_description_included_when_present(self):
        item = {
            "itemId": "x",
            "title": "Q",
            "description": "Some description",
            "textItem": {},
        }
        result = compact_item(item, 0)
        assert result["description"] == "Some description"

    def test_description_omitted_when_absent(self, sample_form):
        result = compact_item(sample_form["items"][0], 0)
        assert "description" not in result


class TestFindIndexByItemId:
    def test_found(self, sample_form):
        assert find_index_by_item_id(sample_form, "item002") == 1

    def test_not_found_raises(self, sample_form):
        with pytest.raises(SystemExit, match="not found"):
            find_index_by_item_id(sample_form, "nonexistent")


class TestFindIndexByTitle:
    def test_found(self, sample_form):
        assert find_index_by_title(sample_form, "Section header") == 2

    def test_not_found_raises(self, sample_form):
        with pytest.raises(SystemExit, match="not found"):
            find_index_by_title(sample_form, "Nonexistent title")


class TestCmdIndexer:
    def _make_args(self, form_id: str, pattern: str, group=None) -> types.SimpleNamespace:
        return types.SimpleNamespace(form_id=form_id, pattern=pattern, group=group)

    def test_default_pattern_matches(self, sample_form, tmp_path, monkeypatch, capsys):
        form_file = tmp_path / f"{sample_form['formId']}.json"
        form_file.write_text(json.dumps(sample_form))

        import suitewright.forms.query as query_mod

        monkeypatch.setattr(query_mod, "cache_path", lambda fid: tmp_path / f"{fid}.json")

        args = self._make_args(sample_form["formId"], DEFAULT_LABEL_PATTERN)
        cmd_indexer(args)
        out = json.loads(capsys.readouterr().out)
        assert out["matchCount"] == 2
        labels = [m["label"] for m in out["matches"]]
        assert "A1." in labels
        assert "B2." in labels

    def test_no_matches(self, sample_form, tmp_path, monkeypatch, capsys):
        form_file = tmp_path / f"{sample_form['formId']}.json"
        form_file.write_text(json.dumps(sample_form))

        import suitewright.forms.query as query_mod

        monkeypatch.setattr(query_mod, "cache_path", lambda fid: tmp_path / f"{fid}.json")

        args = self._make_args(sample_form["formId"], r"^NOMATCH")
        cmd_indexer(args)
        out = json.loads(capsys.readouterr().out)
        assert out["matchCount"] == 0

    def test_invalid_regex_raises(self, sample_form, tmp_path, monkeypatch):
        form_file = tmp_path / f"{sample_form['formId']}.json"
        form_file.write_text(json.dumps(sample_form))

        import suitewright.forms.query as query_mod

        monkeypatch.setattr(query_mod, "cache_path", lambda fid: tmp_path / f"{fid}.json")

        args = self._make_args(sample_form["formId"], r"[invalid")
        with pytest.raises(SystemExit, match="Invalid regex"):
            cmd_indexer(args)
