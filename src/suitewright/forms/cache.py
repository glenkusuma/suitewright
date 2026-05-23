"""Cache path resolution for Forms cache-first workflows.

Thin wrapper delegating to CacheStore("forms") from the shared _core
subpackage. Preserves the original public API (cache_root, cache_path,
ensure_cache_root) for backward compatibility.
"""

from __future__ import annotations

from suitewright._core.cache import CacheStore

_store = CacheStore("forms")

cache_root = _store.root
cache_path = _store.path
ensure_cache_root = _store.ensure_root
