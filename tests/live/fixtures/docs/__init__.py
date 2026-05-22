"""Fixture selection helper for Google Docs test fixtures.

Provides utilities to load fixtures by capability tag or name,
resolve fixture paths, and query available capabilities from the manifest.

Usage:
    from tests.live.fixtures.docs import load_fixture, load_fixture_by_name
    from tests.live.fixtures.docs import fixture_path, fixture_doc_id

    # Load first fixture that has tables
    doc = load_fixture("tables")

    # Load a specific fixture by name
    doc = load_fixture_by_name("Request for Proposal")

    # Get the path to a fixture file
    path = fixture_path("request-for-proposal")

    # Get the document ID for a fixture
    doc_id = fixture_doc_id("request-for-proposal")
"""

from __future__ import annotations

import json
from pathlib import Path

_FIXTURES_DIR = Path(__file__).resolve().parent

_manifest_cache: dict | None = None


def get_manifest() -> dict:
    """Return the parsed manifest dict (cached after first load).

    Raises:
        FileNotFoundError: If manifest.json does not exist.
        RuntimeError: If manifest.json cannot be parsed as valid JSON.
    """
    global _manifest_cache

    if _manifest_cache is not None:
        return _manifest_cache

    manifest_path = _FIXTURES_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest file not found: {manifest_path}. "
            "Run the fixture download script to generate fixtures."
        )

    try:
        _manifest_cache = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Failed to parse manifest at {manifest_path}: {e}"
        ) from e

    return _manifest_cache


def load_fixture(capability: str) -> dict:
    """Load the first fixture matching the given capability tag.

    Args:
        capability: A capability tag (e.g. "tables", "inline_images",
                    "positioned_images", "lists", "headers", "footers",
                    "heading_1", "heading_2", "heading_3").

    Returns:
        Parsed JSON dict of the Google Docs API response.

    Raises:
        ValueError: If no fixture has the requested capability.
        FileNotFoundError: If the fixture file does not exist on disk.
    """
    manifest = get_manifest()

    for entry in manifest.get("fixtures", []):
        if capability in entry.get("capabilities", []):
            fixture_file = _FIXTURES_DIR / entry["file"]
            if not fixture_file.exists():
                raise FileNotFoundError(
                    f"Fixture file not found: {fixture_file} "
                    f"(for fixture '{entry['name']}')"
                )
            return json.loads(fixture_file.read_text(encoding="utf-8"))

    all_caps = available_capabilities()
    raise ValueError(
        f"No fixture found with capability '{capability}'. "
        f"Available capabilities: {all_caps}"
    )


def load_fixture_by_name(name: str) -> dict:
    """Load a specific fixture by its human-readable name.

    Args:
        name: Fixture name as it appears in manifest
              (e.g. "Request for Proposal", "Brochure").

    Returns:
        Parsed JSON dict of the Google Docs API response.

    Raises:
        ValueError: If no fixture matches the given name.
        FileNotFoundError: If the fixture file does not exist on disk.
    """
    manifest = get_manifest()

    for entry in manifest.get("fixtures", []):
        if entry.get("name") == name:
            fixture_file = _FIXTURES_DIR / entry["file"]
            if not fixture_file.exists():
                raise FileNotFoundError(
                    f"Fixture file not found: {fixture_file} "
                    f"(for fixture '{name}')"
                )
            return json.loads(fixture_file.read_text(encoding="utf-8"))

    all_names = [e["name"] for e in manifest.get("fixtures", [])]
    raise ValueError(
        f"No fixture found with name '{name}'. "
        f"Available fixtures: {all_names}"
    )


def fixture_path(slug: str) -> Path:
    """Return the absolute path to a fixture JSON file.

    Args:
        slug: The fixture slug (e.g. "request-for-proposal", "brochure").

    Returns:
        Absolute Path to tests/live/fixtures/docs/{slug}.json.

    Raises:
        FileNotFoundError: If the fixture file does not exist on disk.
    """
    path = _FIXTURES_DIR / f"{slug}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fixture file not found: {path}")
    return path


def fixture_doc_id(slug: str) -> str:
    """Return the document ID for a fixture by slug.

    Args:
        slug: The fixture slug (e.g. "request-for-proposal", "brochure").

    Returns:
        The documentId string from the manifest.

    Raises:
        ValueError: If no fixture matches the slug.
    """
    manifest = get_manifest()
    for entry in manifest.get("fixtures", []):
        # Match by file stem (slug.json -> slug)
        file_stem = entry["file"].removesuffix(".json")
        if file_stem == slug:
            return entry["doc_id"]

    available = [e["file"].removesuffix(".json") for e in manifest.get("fixtures", [])]
    raise ValueError(
        f"No fixture found with slug '{slug}'. "
        f"Available: {available}"
    )


def available_capabilities() -> list[str]:
    """Return sorted list of all capability tags across all fixtures."""
    manifest = get_manifest()
    caps: set[str] = set()
    for entry in manifest.get("fixtures", []):
        caps.update(entry.get("capabilities", []))
    return sorted(caps)


def _reset_cache() -> None:
    """Reset the manifest cache. Used for testing only."""
    global _manifest_cache
    _manifest_cache = None
