"""Live e2e preflight runner for suitewright.

Runs the full live test sequence (smoke -> mutate -> destructive -> e2e -> check_leaks)
with filelock enforcement, refusing to run without SUITEWRIGHT_RUN_LIVE=1.

Usage:
    SUITEWRIGHT_RUN_LIVE=1 uv run python tests/live/scripts/preflight-live.py

Requirements: 15.AC1-15.AC6

Works on Linux, macOS, and Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = REPO_ROOT / "_local" / "tests" / "live" / ".runs"
LOCK_PATH = RUNS_DIR / "live-account.lock"


def _abort(msg: str) -> None:
    """Print error and exit non-zero."""
    print(f"ABORT: {msg}", file=sys.stderr)
    sys.exit(1)


def _check_env_gate() -> None:
    """Refuse to run unless SUITEWRIGHT_RUN_LIVE=1 is set (AC1)."""
    if os.environ.get("SUITEWRIGHT_RUN_LIVE") != "1":
        _abort(
            "SUITEWRIGHT_RUN_LIVE=1 must be set in the environment.\n"
            "  This script runs live tests against a real Google account.\n"
            "  Set the variable explicitly to confirm intent."
        )


def _run_stage(
    name: str,
    marker: str,
    log_path: Path,
    test_dir: str = "tests/live/",
) -> bool:
    """Run a pytest stage with --run-live and redirect output to a log file.

    Returns True if the stage passed, False otherwise.
    """
    cmd = [
        "uv",
        "run",
        "pytest",
        test_dir,
        "-m",
        marker,
        "--run-live",
        "-v",
    ]

    print(f"  [{name}] running: {' '.join(cmd)}")
    print(f"  [{name}] log: {log_path}")

    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as log_file:
        result = subprocess.run(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=REPO_ROOT,
        )

    if result.returncode == 0:
        print(f"  [{name}] PASS")
        return True
    elif result.returncode == 5:
        # pytest exit code 5 = no tests collected; treat as pass for optional stages
        print(f"  [{name}] PASS (no tests collected)")
        return True
    else:
        print(f"  [{name}] FAIL (exit code {result.returncode})")
        return False


def _run_check_leaks(log_path: Path) -> bool:
    """Run check_leaks.py and abort if namespace-prefixed resources are found (AC5).

    Returns True if clean, False if leaks detected.
    """
    cmd = ["uv", "run", "python", "tests/live/scripts/check_leaks.py"]

    print(f"  [check_leaks] running: {' '.join(cmd)}")
    print(f"  [check_leaks] log: {log_path}")

    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as log_file:
        result = subprocess.run(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=REPO_ROOT,
        )

    if result.returncode == 0:
        print("  [check_leaks] PASS — no leaks detected")
        return True
    else:
        print("  [check_leaks] FAIL — namespace-prefixed resources found!")
        print(f"  See log for details: {log_path}")
        return False


def main() -> None:
    # AC1: Refuse to run without SUITEWRIGHT_RUN_LIVE=1
    _check_env_gate()

    # Prepare log directory with timestamp
    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    log_dir = RUNS_DIR / f"preflight-live-{ts}"
    log_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("suitewright live e2e preflight")
    print(f"  timestamp: {ts}")
    print(f"  logs:      {log_dir}")
    print("=" * 60)
    print()

    # AC2: Acquire filelock
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(LOCK_PATH, timeout=1)

    try:
        lock.acquire()
    except Timeout:
        _abort(
            f"Could not acquire filelock at {LOCK_PATH}.\n"
            "  Another live test session is already running.\n"
            "  Wait for it to finish or remove the stale lock file."
        )

    # AC6: Release filelock on completion or error (try/finally)
    try:
        # AC3: Run 5 stages in order
        stages = [
            ("smoke", "smoke"),
            ("mutate", "mutate"),
            ("destructive", "destructive"),
            ("e2e", "live and not smoke and not mutate and not destructive"),
        ]

        all_passed = True

        for name, marker in stages:
            log_path = log_dir / f"{name}.log"
            passed = _run_stage(name, marker, log_path)
            if not passed:
                all_passed = False
                print(f"\n  Stage '{name}' failed. Continuing remaining stages...")

        # AC5: Run check_leaks — abort if namespace-prefixed resources found
        leaks_log = log_dir / "check_leaks.log"
        leaks_clean = _run_check_leaks(leaks_log)
        if not leaks_clean:
            all_passed = False
            _abort(
                "check_leaks detected namespace-prefixed resources remaining.\n"
                f"  See: {leaks_log}\n"
                "  Clean up manually before retrying."
            )

        # Summary
        print()
        print("=" * 60)
        if all_passed:
            print("All live e2e stages passed.")
        else:
            print("Some stages failed. Review logs above.")
            sys.exit(1)

    finally:
        # AC6: Release filelock on completion or error
        lock.release()


if __name__ == "__main__":
    main()
