"""Idempotent first-time setup for suitewright live tests.

Usage:
    uv run python tests/live/scripts/bootstrap.py
    HEADLESS=1 uv run python tests/live/scripts/bootstrap.py

Works on Linux, macOS, and Windows.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LIVE_DIR = REPO_ROOT / "tests" / "live"
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _uv(*args: str, capture: bool = False, check: bool = False) -> subprocess.CompletedProcess:
    cmd = ["uv", "run", "suitewright", *args]
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        cwd=REPO_ROOT,
        check=check,
    )


def _uv_json(*args: str) -> dict | list:
    result = _uv(*args, capture=True)
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def main() -> None:
    # 1. Check uv is available
    if not shutil.which("uv"):
        print("ERROR: uv is required but not on PATH.", file=sys.stderr)
        print("Install from https://docs.astral.sh/uv/", file=sys.stderr)
        sys.exit(1)

    # 2. Ensure tests/live/.env exists
    if not ENV_FILE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        print("Created tests/live/.env from template.")
        print(
            "Edit it and set SUITEWRIGHT_LIVE_TEST_CLIENT_SECRET, then re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Load .env into os.environ (without overriding existing values)
    sys.path.insert(0, str(REPO_ROOT))
    from tests.live.helpers import parse_dotenv

    parsed = parse_dotenv(ENV_FILE)
    for key, value in parsed.items():
        if value and key not in os.environ:
            os.environ[key] = value

    # 4. Validate client secret
    secret_path = os.environ.get("SUITEWRIGHT_LIVE_TEST_CLIENT_SECRET", "")
    if not secret_path:
        print(
            "ERROR: SUITEWRIGHT_LIVE_TEST_CLIENT_SECRET not set in tests/live/.env",
            file=sys.stderr,
        )
        sys.exit(1)
    secret_file = Path(secret_path).expanduser()
    if not secret_file.is_absolute():
        secret_file = REPO_ROOT / secret_file
    if not secret_file.exists():
        print(f"ERROR: client secret not found at: {secret_file}", file=sys.stderr)
        print("Download an OAuth desktop client secret from Google Cloud Console:", file=sys.stderr)
        print("  https://console.cloud.google.com/apis/credentials", file=sys.stderr)
        sys.exit(1)

    # 5. Auth init (idempotent)
    print("==> suitewright auth init")
    _uv("auth", "init", "--client-secret", str(secret_file))

    # 6. Login
    headless = os.environ.get("HEADLESS", "0") == "1"
    if headless:
        print("==> suitewright auth login --auth-url (headless)")
        _uv("auth", "login", "--auth-url")
        print()
        print("Complete consent in a browser, then run:")
        print("  uv run suitewright auth login --auth-code 'PASTED_URL_OR_CODE'")
        print("Then re-run this script (without HEADLESS=1) to verify.")
        sys.exit(0)

    # Check if token is already valid — skip login if so
    check_result = _uv("auth", "check", capture=True)
    if check_result.returncode == 0:
        print("==> existing token is valid, skipping login")
    else:
        print("==> suitewright auth login (interactive)")
        # Inherit stdin/stdout so the user can paste the auth code
        login_result = subprocess.run(
            ["uv", "run", "suitewright", "auth", "login"],
            cwd=REPO_ROOT,
        )
        if login_result.returncode != 0:
            sys.exit(login_result.returncode)

    # 7. Auth check — print result
    print("==> suitewright auth check")
    _uv("auth", "check")

    # 8. Sandbox root folder (idempotent)
    print("==> Checking sandbox root folder...")
    root_folder_id = os.environ.get("SUITEWRIGHT_LIVE_TEST_ROOT_FOLDER_ID", "")
    if not root_folder_id:
        print(
            "No SUITEWRIGHT_LIVE_TEST_ROOT_FOLDER_ID set — creating 'suitewright-tests' folder..."
        )
        folder = _uv_json("drive", "create-folder", "suitewright-tests")
        new_id = folder["id"]
        print()
        print(f"Created Drive folder 'suitewright-tests' with ID: {new_id}")
        print("Add this to tests/live/.env:")
        print(f"  SUITEWRIGHT_LIVE_TEST_ROOT_FOLDER_ID={new_id}")
        print()
        print("Then re-run this script to verify.")
    else:
        verify = _uv("drive", "get", root_folder_id, capture=True)
        if verify.returncode == 0:
            print(f"OK: Root folder {root_folder_id} exists.")
        else:
            print(f"ERROR: Root folder {root_folder_id} not found in Drive.", file=sys.stderr)
            print(
                "It may have been deleted. Remove SUITEWRIGHT_LIVE_TEST_ROOT_FOLDER_ID "
                "from .env and re-run to create a new one.",
                file=sys.stderr,
            )
            sys.exit(1)

    print()
    print("Bootstrap complete. Next steps:")
    print("  uv run pytest tests/live/ -m smoke --run-live")
    print("  uv run pytest tests/live/ --run-live   # full sweep")
    print("  uv run python tests/live/scripts/check_leaks.py")


if __name__ == "__main__":
    main()
