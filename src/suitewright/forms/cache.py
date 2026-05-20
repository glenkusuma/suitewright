"""Cache path resolution for Forms cache-first workflows."""

from __future__ import annotations

from pathlib import Path

from suitewright import paths


def cache_root() -> Path:
    return paths.resolve("cache_dir") / "forms"


def cache_path(form_id: str) -> Path:
    return cache_root() / f"{form_id}.json"


def ensure_cache_root() -> Path:
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    return root
