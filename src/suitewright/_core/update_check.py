"""Non-blocking update check against PyPI.

Queries https://pypi.org/pypi/suitewright/json for the latest version and
prints a notice to stderr if the installed version is older. Results are
cached locally for 24 hours to avoid repeated network calls.

Disable with: SUITEWRIGHT_NO_UPDATE_CHECK=1
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _cache_path() -> Path:
    cache_dir = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache_dir) / "suitewright" / "update-check.json"


def _read_cache() -> dict | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("checked_at", 0) < 86400:
            return data
    except Exception:
        pass
    return None


def _write_cache(latest: str) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(
            json.dumps({"latest": latest, "checked_at": time.time()}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _fetch_latest() -> str | None:
    import urllib.request

    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/suitewright/json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:  # nosec B310  # noqa: S310
            data = json.loads(resp.read())
            return data.get("info", {}).get("version")
    except Exception:
        return None


def _is_newer(latest: str, current: str) -> bool:
    try:
        from packaging.version import Version

        return Version(latest) > Version(current)
    except Exception:
        # Fallback: simple string comparison (works for most semver)
        return latest != current and latest > current


def check_for_update(current_version: str) -> None:
    """Print update notice to stderr if a newer version exists on PyPI.

    Safe to call unconditionally - catches all exceptions and respects
    SUITEWRIGHT_NO_UPDATE_CHECK=1 to disable.
    """
    if os.environ.get("SUITEWRIGHT_NO_UPDATE_CHECK"):
        return

    try:
        cached = _read_cache()
        if cached:
            latest = cached["latest"]
        else:
            latest = _fetch_latest()
            if latest:
                _write_cache(latest)

        if latest and _is_newer(latest, current_version):
            print(
                f"Update available: {current_version} -> {latest}. "
                f"Run: pip install --upgrade suitewright",
                file=sys.stderr,
            )
    except Exception:
        pass
