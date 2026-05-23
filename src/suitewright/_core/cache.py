"""Shared cache store for Google Workspace resource caching."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from suitewright._core import paths


class CacheStore:
    """Cache store for a specific service (forms, docs, etc.).

    Provides path resolution, atomic writes, SHA-256 hashing, and
    load/exists helpers for JSON cache files.
    """

    def __init__(self, service_name: str) -> None:
        self._service_name = service_name

    def root(self) -> Path:
        """Return the cache root directory for this service."""
        return paths.resolve("cache_dir") / self._service_name

    def path(self, resource_id: str) -> Path:
        """Return the cache file path for a specific resource."""
        return self.root() / f"{resource_id}.json"

    def ensure_root(self) -> Path:
        """Create the cache root directory if it doesn't exist."""
        root = self.root()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def load(self, resource_id: str) -> dict:
        """Load cached JSON. Raises FileNotFoundError if missing."""
        p = self.path(resource_id)
        if not p.exists():
            raise FileNotFoundError(
                f"Cache not found for '{resource_id}'. "
                f"Run `{self._service_name} cache fetch` first. "
                f"Expected path: {p}"
            )
        return json.loads(p.read_text(encoding="utf-8"))

    def write(self, resource_id: str, payload: dict) -> Path:
        """Write JSON to cache file (atomic: write to .tmp then rename).

        Ensures the root directory exists, writes to a temporary file,
        then atomically renames to the target path.
        """
        self.ensure_root()
        target = self.path(resource_id)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
        return target

    def hash(self, resource_id: str) -> str:
        """Compute SHA-256 hex digest of the cache file bytes.

        Raises FileNotFoundError if the cache file does not exist.
        """
        p = self.path(resource_id)
        if not p.exists():
            raise FileNotFoundError(
                f"Cache not found for '{resource_id}'. "
                f"Run `{self._service_name} cache fetch` first."
            )
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def exists(self, resource_id: str) -> bool:
        """Check if a cache file exists for the given resource."""
        return self.path(resource_id).exists()
