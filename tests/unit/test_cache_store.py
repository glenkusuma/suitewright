"""Tests for suitewright._core.cache — CacheStore class."""

from __future__ import annotations

import hashlib

import pytest

from suitewright._core.cache import CacheStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Create a CacheStore with cache_dir pointing to tmp_path."""
    monkeypatch.setenv("SUITEWRIGHT_CACHE_DIR", str(tmp_path))
    return CacheStore("testservice")


class TestRootAndPath:
    def test_root_returns_service_subdirectory(self, store, tmp_path):
        assert store.root() == tmp_path / "testservice"

    def test_path_returns_json_file(self, store, tmp_path):
        assert store.path("abc123") == tmp_path / "testservice" / "abc123.json"


class TestEnsureRoot:
    def test_creates_directory_if_missing(self, store, tmp_path):
        root = store.ensure_root()
        assert root.is_dir()
        assert root == tmp_path / "testservice"

    def test_idempotent_when_exists(self, store):
        store.ensure_root()
        store.ensure_root()  # Should not raise
        assert store.root().is_dir()


class TestRoundTrip:
    def test_write_then_load_returns_same_data(self, store):
        payload = {"documentId": "doc1", "title": "Test Doc", "body": {"content": []}}
        store.write("doc1", payload)
        loaded = store.load("doc1")
        assert loaded == payload

    def test_write_preserves_unicode(self, store):
        payload = {"title": "Tes Dokumen — Ñoño 日本語"}
        store.write("unicode-doc", payload)
        loaded = store.load("unicode-doc")
        assert loaded["title"] == "Tes Dokumen — Ñoño 日本語"

    def test_write_overwrites_existing(self, store):
        store.write("doc1", {"version": 1})
        store.write("doc1", {"version": 2})
        loaded = store.load("doc1")
        assert loaded == {"version": 2}

    def test_write_returns_target_path(self, store, tmp_path):
        path = store.write("doc1", {"data": True})
        assert path == tmp_path / "testservice" / "doc1.json"
        assert path.exists()


class TestHashCorrectness:
    def test_hash_matches_sha256_of_file_bytes(self, store):
        payload = {"documentId": "doc1", "title": "Hash Test"}
        store.write("doc1", payload)

        # Compute expected hash from the file bytes directly
        file_bytes = store.path("doc1").read_bytes()
        expected = hashlib.sha256(file_bytes).hexdigest()

        assert store.hash("doc1") == expected

    def test_hash_changes_when_content_changes(self, store):
        store.write("doc1", {"version": 1})
        hash1 = store.hash("doc1")

        store.write("doc1", {"version": 2})
        hash2 = store.hash("doc1")

        assert hash1 != hash2

    def test_hash_is_64_char_hex_string(self, store):
        store.write("doc1", {"data": "test"})
        h = store.hash("doc1")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestAtomicWrite:
    def test_no_tmp_file_remains_after_write(self, store):
        store.write("doc1", {"data": "test"})
        tmp_file = store.path("doc1").with_suffix(".json.tmp")
        assert not tmp_file.exists()

    def test_target_file_exists_after_write(self, store):
        store.write("doc1", {"data": "test"})
        assert store.path("doc1").exists()

    def test_write_creates_root_directory(self, store, tmp_path):
        # Root doesn't exist yet
        assert not (tmp_path / "testservice").exists()
        store.write("doc1", {"data": "test"})
        assert (tmp_path / "testservice").is_dir()


class TestMissingFileErrors:
    def test_load_raises_file_not_found_error(self, store):
        with pytest.raises(FileNotFoundError, match="Cache not found"):
            store.load("nonexistent")

    def test_load_error_includes_resource_id(self, store):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            store.load("nonexistent")

    def test_load_error_suggests_fetch(self, store):
        with pytest.raises(FileNotFoundError, match="cache fetch"):
            store.load("missing-doc")

    def test_hash_raises_file_not_found_error(self, store):
        with pytest.raises(FileNotFoundError, match="Cache not found"):
            store.hash("nonexistent")

    def test_hash_error_suggests_fetch(self, store):
        with pytest.raises(FileNotFoundError, match="cache fetch"):
            store.hash("missing-doc")


class TestExists:
    def test_exists_returns_false_when_missing(self, store):
        assert store.exists("nonexistent") is False

    def test_exists_returns_true_after_write(self, store):
        store.write("doc1", {"data": "test"})
        assert store.exists("doc1") is True
