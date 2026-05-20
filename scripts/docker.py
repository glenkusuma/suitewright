#!/usr/bin/env python3
"""Docker dev workflow - build and run tests in containers.

Wraps Docker CLI operations for contributor-friendly test execution.
Supports two subcommands: `build` (build the test image) and `test`
(run tests in Docker with optional --live mode for live API tests).

Usage:
    uv run python scripts/docker.py build
    uv run python scripts/docker.py test [--live] [pytest-args...]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# --- Constants ---

IMAGE_NAME = "suitewright-test"
IMAGE_TAG = "local"
IMAGE_REF = f"{IMAGE_NAME}:{IMAGE_TAG}"
DOCKERFILE = "Dockerfile.test"
DEFAULT_AUTH_DIR = "../suitewright-auth"
PREFIX = "docker"
REPO_ROOT = Path(__file__).resolve().parents[1]


# --- Utilities ---


def msg(text: str) -> None:
    """Print a prefixed status message to stderr."""
    print(f"{PREFIX}: {text}", file=sys.stderr)


def err(text: str) -> None:
    """Print a prefixed error message to stderr with remediation hint."""
    print(f"{PREFIX}: Error: {text}", file=sys.stderr)


def check_docker() -> None:
    """Verify docker is on PATH and daemon is running. Calls sys.exit on failure."""
    if shutil.which("docker") is None:
        err("Docker not found on PATH.")
        msg("Hint: Install Docker: https://docs.docker.com/get-docker/")
        sys.exit(1)

    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err("Docker daemon is not running.")
        msg("Hint: Start Docker daemon or open Docker Desktop")
        sys.exit(1)


def check_image() -> None:
    """Verify suitewright-test:local exists locally. Calls sys.exit on failure."""
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE_REF],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err(f"Test image '{IMAGE_REF}' not found locally.")
        msg("Hint: Build first: `uv run python scripts/docker.py build`")
        sys.exit(1)


def run_preflight() -> None:
    """Run preflight scripts locally before launching live Docker tests.

    Calls sys.exit on failure with the failing script's exit code.
    """
    scripts = [
        ("preflight", ["uv", "run", "python", "tests/live/scripts/preflight.py"]),
        ("preflight-live", ["uv", "run", "python", "tests/live/scripts/preflight-live.py"]),
    ]
    for name, cmd in scripts:
        msg(f"Running {name}...")
        result = subprocess.run(cmd, cwd=str(REPO_ROOT))
        if result.returncode != 0:
            err(f"Preflight check failed: {name}")
            sys.exit(result.returncode)


# --- Subcommands ---


def cmd_build() -> int:
    """Build the test Docker image. Returns exit code."""
    check_docker()

    result = subprocess.run(
        ["docker", "build", "-t", IMAGE_REF, "-f", DOCKERFILE, "."],
        cwd=str(REPO_ROOT),
    )

    if result.returncode == 0:
        msg(f"Image built: {IMAGE_NAME}:{IMAGE_TAG}")

    return result.returncode


def cmd_test(args: list[str]) -> int:
    """Run tests in Docker. Handles --live flag internally. Returns exit code."""
    check_docker()
    check_image()

    live = "--live" in args
    forward_args = [a for a in args if a != "--live"]

    if live:
        run_preflight()

        # Resolve auth directory
        auth_dir = Path(
            os.environ.get("SUITEWRIGHT_AUTH_DIR", str(REPO_ROOT / DEFAULT_AUTH_DIR))
        ).resolve()

        # Validate auth directory exists
        if not auth_dir.is_dir():
            err(f"Auth directory not found: {auth_dir}")
            msg("Hint: Set up credentials or set SUITEWRIGHT_AUTH_DIR")
            sys.exit(1)

        # Validate .env file exists
        env_file = REPO_ROOT / ".env"
        if not env_file.is_file():
            err(f".env file not found: {env_file}")
            msg("Hint: Create from template: `cp .env.example .env`")
            sys.exit(1)

        # Ensure writable mount targets exist
        (REPO_ROOT / "cache").mkdir(parents=True, exist_ok=True)
        (REPO_ROOT / "_local").mkdir(parents=True, exist_ok=True)

        # Construct live mode docker run command
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            "suitewright-test-live",
            "-v",
            f"{REPO_ROOT / 'tests'}:/app/tests:ro",
            "-v",
            f"{auth_dir}:/app/suitewright-auth:ro",
            "-v",
            f"{env_file}:/app/.env:ro",
            "-v",
            f"{REPO_ROOT / 'cache'}:/app/cache",
            "-v",
            f"{REPO_ROOT / '_local'}:/app/_local",
            "-e",
            "SUITEWRIGHT_AUTH_DIR=/app/suitewright-auth",
            "-e",
            "NO_COLOR=1",
            IMAGE_REF,
            "pytest",
            "tests/live/",
            "--run-live",
            *forward_args,
        ]

        result = subprocess.run(cmd)
        return result.returncode

    # Default mode: run unit/integration tests (excluding tests/live/ and tests/scripts/)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        "suitewright-test",
        "-v",
        f"{REPO_ROOT / 'tests'}:/app/tests:ro",
        IMAGE_REF,
        "pytest",
        "tests/",
        "--ignore=tests/live",
        "--ignore=tests/scripts",
        *forward_args,
    ]

    result = subprocess.run(cmd)
    return result.returncode


# --- Main ---


def main() -> None:
    """Dispatch subcommand from sys.argv."""
    if len(sys.argv) < 2:
        err("Usage: uv run python scripts/docker.py {build, test}")
        sys.exit(1)

    subcmd = sys.argv[1]
    extra = sys.argv[2:]

    if subcmd == "build":
        sys.exit(cmd_build())
    elif subcmd == "test":
        sys.exit(cmd_test(extra))
    else:
        err(f"Unknown subcommand: {subcmd}")
        err("Usage: uv run python scripts/docker.py {build, test}")
        sys.exit(1)


if __name__ == "__main__":
    main()
