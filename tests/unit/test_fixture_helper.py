"""Unit tests for the fixture selection helper module."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tests.live.fixtures.docs import (
    _reset_cache,
    available_capabilities,
    fixture_doc_id,
    fixture_path,
    get_manifest,
    load_fixture,
    load_fixture_by_name,
)

SAMPLE_MANIFEST = {
    "schema_version": 1,
    "fixtures": [
        {
            "name": "Request for Proposal",
            "doc_id": "VCvpiJTZ7Sp_V79-Uh486_Yfa5nny8_n3eZkq7W8_bQ2",
            "file": "request-for-proposal.json",
            "capabilities": [
                "paragraphs",
                "tables",
                "inline_images",
                "positioned_images",
                "lists",
                "headers",
                "footers",
                "heading_1",
                "heading_2",
            ],
            "stats": {
                "paragraphs": 106,
                "tables": 1,
                "inline_images": 7,
                "positioned_images": 1,
                "lists": 39,
            },
        },
        {
            "name": "Brochure",
            "doc_id": "dfk5_IJW13ua5oPKct6chax7wsFvckiI7fdonhwFNdu7",
            "file": "brochure.json",
            "capabilities": [
                "paragraphs",
                "positioned_images",
                "headers",
                "footers",
                "heading_1",
                "heading_2",
                "heading_3",
            ],
            "stats": {
                "paragraphs": 17,
                "tables": 0,
                "inline_images": 0,
                "positioned_images": 5,
                "lists": 0,
            },
        },
        {
            "name": "Recipe",
            "doc_id": "qYMz5Wyno4ETlcCA3elpPXFItlsIWI_mUZNfxkgnwLzU",
            "file": "recipe.json",
            "capabilities": [
                "paragraphs",
                "inline_images",
                "lists",
                "heading_1",
            ],
            "stats": {
                "paragraphs": 20,
                "tables": 0,
                "inline_images": 1,
                "positioned_images": 0,
                "lists": 5,
            },
        },
    ],
}


@pytest.fixture(autouse=True)
def _clear_cache():
    _reset_cache()
    yield
    _reset_cache()


@pytest.fixture()
def mock_manifest(tmp_path):
    """Create a temporary manifest and fixture files."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(SAMPLE_MANIFEST), encoding="utf-8")

    for entry in SAMPLE_MANIFEST["fixtures"]:
        fixture_file = tmp_path / entry["file"]
        doc_content = {
            "title": entry["name"],
            "body": {"content": []},
        }
        fixture_file.write_text(json.dumps(doc_content), encoding="utf-8")

    with patch("tests.live.fixtures.docs._FIXTURES_DIR", tmp_path):
        yield tmp_path


class TestGetManifest:
    def test_loads_manifest(self, mock_manifest):
        manifest = get_manifest()
        assert manifest["schema_version"] == 1
        assert len(manifest["fixtures"]) == 3

    def test_caches_on_second_call(self, mock_manifest):
        manifest1 = get_manifest()
        manifest2 = get_manifest()
        assert manifest1 is manifest2

    def test_raises_file_not_found_when_missing(self, tmp_path):
        with patch("tests.live.fixtures.docs._FIXTURES_DIR", tmp_path):
            with pytest.raises(FileNotFoundError, match="Manifest file not found"):
                get_manifest()

    def test_raises_runtime_error_on_invalid_json(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("not valid json {{{", encoding="utf-8")
        with patch("tests.live.fixtures.docs._FIXTURES_DIR", tmp_path):
            with pytest.raises(RuntimeError, match="Failed to parse manifest"):
                get_manifest()


class TestLoadFixture:
    def test_returns_first_match(self, mock_manifest):
        doc = load_fixture("tables")
        assert doc["title"] == "Request for Proposal"

    def test_returns_first_when_multiple_match(self, mock_manifest):
        doc = load_fixture("paragraphs")
        assert doc["title"] == "Request for Proposal"

    def test_unique_capability(self, mock_manifest):
        doc = load_fixture("heading_3")
        assert doc["title"] == "Brochure"

    def test_raises_value_error_for_unknown(self, mock_manifest):
        with pytest.raises(ValueError, match="No fixture found with capability"):
            load_fixture("charts")

    def test_raises_file_not_found_when_file_missing(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(SAMPLE_MANIFEST), encoding="utf-8")
        with patch("tests.live.fixtures.docs._FIXTURES_DIR", tmp_path):
            with pytest.raises(FileNotFoundError, match="Fixture file not found"):
                load_fixture("tables")


class TestLoadFixtureByName:
    def test_returns_correct_fixture(self, mock_manifest):
        doc = load_fixture_by_name("Brochure")
        assert doc["title"] == "Brochure"

    def test_raises_value_error_for_unknown(self, mock_manifest):
        with pytest.raises(ValueError, match="No fixture found with name"):
            load_fixture_by_name("Unknown Doc")

    def test_exact_match_required(self, mock_manifest):
        with pytest.raises(ValueError):
            load_fixture_by_name("brochure")


class TestFixturePath:
    def test_returns_absolute_path(self, mock_manifest):
        path = fixture_path("request-for-proposal")
        assert path.is_absolute()
        assert path.name == "request-for-proposal.json"

    def test_raises_file_not_found(self, mock_manifest):
        with pytest.raises(FileNotFoundError):
            fixture_path("nonexistent")


class TestFixtureDocId:
    def test_returns_doc_id(self, mock_manifest):
        doc_id = fixture_doc_id("request-for-proposal")
        assert doc_id == "VCvpiJTZ7Sp_V79-Uh486_Yfa5nny8_n3eZkq7W8_bQ2"

    def test_returns_correct_id_for_each(self, mock_manifest):
        assert fixture_doc_id("brochure") == "dfk5_IJW13ua5oPKct6chax7wsFvckiI7fdonhwFNdu7"
        assert fixture_doc_id("recipe") == "qYMz5Wyno4ETlcCA3elpPXFItlsIWI_mUZNfxkgnwLzU"

    def test_raises_value_error_for_unknown(self, mock_manifest):
        with pytest.raises(ValueError, match="No fixture found with slug"):
            fixture_doc_id("nonexistent")


class TestAvailableCapabilities:
    def test_returns_sorted_list(self, mock_manifest):
        caps = available_capabilities()
        assert caps == sorted(caps)

    def test_returns_all_unique(self, mock_manifest):
        caps = available_capabilities()
        expected = sorted({
            "paragraphs", "tables", "inline_images", "positioned_images",
            "lists", "headers", "footers", "heading_1", "heading_2", "heading_3",
        })
        assert caps == expected

    def test_empty_manifest(self, tmp_path):
        empty_manifest = {"schema_version": 1, "fixtures": []}
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(empty_manifest), encoding="utf-8")
        with patch("tests.live.fixtures.docs._FIXTURES_DIR", tmp_path):
            assert available_capabilities() == []
