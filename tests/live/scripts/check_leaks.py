"""Check for ephemeral artifact leaks from suitewright live tests.

Exits 0 if clean. Exits 1 and prints details if any of the following are found:
  - Drive resources matching the sandbox prefix still exist
  - Gmail messages matching the sandbox prefix still exist
  - Calendar events matching the sandbox prefix still exist
  - Forms cache files matching the sandbox prefix still exist
  - leaked.json files in _local/tests/live/.runs/
  - cleanup.json entries with ok:false

Namespace convention:
  Resources are named with the prefix (default: suitewright-live-test):
    Drive:    "{prefix}-{run_id}" folders, "{prefix}-{slug}-{uuid}" files
    Gmail:    subject contains "[{prefix}]"
    Calendar: summary contains "[{prefix}]"
    Forms:    cache files for forms created with "{prefix}-" title prefix

Usage:
    uv run python tests/live/scripts/check_leaks.py

Works on Linux, macOS, and Windows.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LIVE_DIR = REPO_ROOT / "tests" / "live"
ENV_FILE = LIVE_DIR / ".env"
RUNS_DIR = REPO_ROOT / "_local" / "tests" / "live" / ".runs"


def _uv_json(*args: str) -> list | dict:
    result = subprocess.run(
        ["uv", "run", "suitewright", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def _check_drive(prefix: str) -> bool:
    """Check for leaked Drive resources matching the sandbox prefix."""
    print(f"==> Checking Drive for leaked sandbox resources (prefix: {prefix})...")
    results = _uv_json("drive", "search", prefix, "--max", "50")
    if isinstance(results, list) and results:
        print(f"LEAK: {len(results)} Drive resource(s) found matching '{prefix}':")
        for item in results:
            print(f"  {item.get('id')} — {item.get('name')} ({item.get('mimeType', '')})")
        return True
    print("OK: No Drive leaks.")
    return False


def _check_gmail(prefix: str) -> bool:
    """Check for leaked Gmail messages matching the sandbox prefix."""
    print(f"==> Checking Gmail for leaked messages (prefix: [{prefix}])...")
    query = f"subject:[{prefix}]"
    results = _uv_json("gmail", "search", query, "--max", "50")
    if isinstance(results, list) and results:
        print(f"LEAK: {len(results)} Gmail message(s) found matching '{query}':")
        for msg in results:
            print(f"  {msg.get('id')} — {msg.get('subject', '(no subject)')}")
        return True
    print("OK: No Gmail leaks.")
    return False


def _check_calendar(prefix: str, calendar_id: str) -> bool:
    """Check for leaked Calendar events matching the sandbox prefix."""
    print(f"==> Checking Calendar for leaked events (prefix: [{prefix}])...")
    # Search a wide window (past 30 days to next 30 days) for leaked events
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    start = (now - timedelta(days=30)).isoformat()
    end = (now + timedelta(days=30)).isoformat()

    results = _uv_json(
        "calendar",
        "list",
        "--calendar",
        calendar_id,
        "--start",
        start,
        "--end",
        end,
        "--max",
        "100",
    )
    if not isinstance(results, list):
        print("OK: No Calendar leaks (could not list events).")
        return False

    leaked = [e for e in results if prefix in e.get("summary", "")]
    if leaked:
        print(f"LEAK: {len(leaked)} Calendar event(s) found matching '[{prefix}]':")
        for event in leaked:
            print(f"  {event.get('id')} — {event.get('summary', '(no title)')}")
        return True
    print("OK: No Calendar leaks.")
    return False


def _check_forms_cache(prefix: str) -> bool:
    """Check for leaked Forms cache files matching the sandbox prefix.

    Forms created by live tests have titles starting with the prefix.
    Their cache files are stored by form ID, so we check the cache contents
    for form titles matching the prefix pattern.
    """
    print(f"==> Checking Forms cache for leaked entries (prefix: {prefix})...")
    # Resolve the forms cache directory
    cache_dir = REPO_ROOT / "cache" / "forms"
    if not cache_dir.exists():
        # Try XDG/default cache locations
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            cache_dir = Path(xdg_cache) / "suitewright" / "forms"
        else:
            cache_dir = Path.home() / ".cache" / "suitewright" / "forms"

    if not cache_dir.exists():
        print("OK: No Forms cache directory found.")
        return False

    leaked = []
    for cache_file in cache_dir.glob("*.json"):
        try:
            data = json.loads(cache_file.read_text())
            info = data.get("info", {})
            title = info.get("title", "")
            if title.startswith(prefix):
                leaked.append((cache_file.name, title))
        except (json.JSONDecodeError, OSError):
            pass

    if leaked:
        print(f"LEAK: {len(leaked)} Forms cache file(s) matching prefix '{prefix}':")
        for filename, title in leaked:
            print(f"  {filename} — {title}")
        return True
    print("OK: No Forms cache leaks.")
    return False


def _check_leaked_json() -> bool:
    """Check for leaked.json files in run artifacts."""
    print("==> Checking run artifacts for leaked.json...")
    leaked_files = list(RUNS_DIR.glob("*/leaked.json")) if RUNS_DIR.exists() else []
    if leaked_files:
        print("LEAK: leaked.json found:")
        for f in leaked_files:
            print(f"  {f}:")
            print(f.read_text())
        return True
    print("OK: No leaked.json files.")
    return False


def _check_cleanup_json() -> bool:
    """Check cleanup.json for failed teardown entries."""
    print("==> Checking cleanup.json for failed teardown entries...")
    cleanup_files = list(RUNS_DIR.glob("*/cleanup.json")) if RUNS_DIR.exists() else []
    failed = False
    for f in cleanup_files:
        try:
            data = json.loads(f.read_text())
            bad = [e for e in data if not e.get("ok", True)]
            if bad:
                print(f"FAIL: {f} has failed teardown entries:")
                print(json.dumps(bad, indent=2))
                failed = True
        except (json.JSONDecodeError, OSError):
            pass
    if not failed:
        print("OK: All cleanup.json entries are clean.")
    return failed


def main() -> None:
    # Load .env if present (don't fail if missing)
    sys.path.insert(0, str(REPO_ROOT))
    from tests.live.helpers import parse_dotenv

    if ENV_FILE.exists():
        parsed = parse_dotenv(ENV_FILE)
        for key, value in parsed.items():
            if value and key not in os.environ:
                os.environ[key] = value

    prefix = os.environ.get("SUITEWRIGHT_LIVE_TEST_PREFIX", "suitewright-live-test")
    calendar_id = os.environ.get("SUITEWRIGHT_LIVE_TEST_CALENDAR_ID", "primary")
    failed = False

    # 1. Drive leak check
    if _check_drive(prefix):
        failed = True

    # 2. Gmail leak check
    if _check_gmail(prefix):
        failed = True

    # 3. Calendar leak check
    if _check_calendar(prefix, calendar_id):
        failed = True

    # 4. Forms cache leak check
    if _check_forms_cache(prefix):
        failed = True

    # 5. leaked.json check
    if _check_leaked_json():
        failed = True

    # 6. cleanup.json check
    if _check_cleanup_json():
        failed = True

    # Summary
    print()
    if not failed:
        print("All checks passed — no leaks detected.")
        sys.exit(0)
    else:
        print("ABORT: Leaks detected. Clean up manually:")
        print("  uv run suitewright drive delete <id> --permanent")
        print("  uv run suitewright gmail trash <id>")
        print(f"  uv run suitewright calendar delete <id> --calendar {calendar_id}")
        print("  rm <cache-dir>/forms/<form-id>.json")
        sys.exit(1)


if __name__ == "__main__":
    main()
