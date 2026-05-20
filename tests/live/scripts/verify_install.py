"""Verify suitewright install across all 4 auth-resolution modes.

Runs 4 scenarios in isolated tempdirs to confirm that `suitewright auth check`
reports the correct resolution mode without touching any real account.

Usage:
    uv run python tests/live/scripts/verify_install.py
    uv run python tests/live/scripts/verify_install.py --installed

Flags:
    --installed   Use the PATH binary directly instead of `uv run`

Works on Linux, macOS, and Windows.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = REPO_ROOT / "_local" / "tests" / "live" / ".runs"

# Dummy auth files — content is irrelevant; only existence matters for mode detection.
DUMMY_TOKEN = json.dumps({"token": "fake", "type": "authorized_user"})
DUMMY_CLIENT_SECRET = json.dumps({"installed": {"client_id": "fake", "client_secret": "fake"}})


def _build_cmd(installed: bool) -> list[str]:
    """Return the base command for invoking suitewright."""
    if installed:
        return ["suitewright"]
    return ["uv", "run", "suitewright"]


def _run_auth_check(
    env: dict[str, str],
    cwd: Path,
    installed: bool,
) -> dict:
    """Run `suitewright auth check` with the given env and return parsed JSON output.

    The command may exit non-zero (e.g. NOT_AUTHENTICATED) but still produce
    valid JSON on stdout — that's expected for isolated scenarios with no real token.
    """
    cmd = [*_build_cmd(installed), "auth", "check"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
    )
    # auth check outputs JSON to stdout regardless of exit code
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "error": "failed to parse output",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }


def _clean_env() -> dict[str, str]:
    """Return a sanitized copy of os.environ without suitewright-specific vars.

    This ensures each scenario starts from a clean slate.
    """
    env = dict(os.environ)
    # Remove all suitewright env vars that could influence resolution
    for key in list(env.keys()):
        if key.startswith("SUITEWRIGHT_"):
            del env[key]
    # Remove XDG vars to avoid cross-contamination
    env.pop("XDG_CONFIG_HOME", None)
    env.pop("XDG_CACHE_HOME", None)
    return env


def _populate_auth_dir(auth_dir: Path) -> None:
    """Create dummy auth files in the given directory."""
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "google_token.json").write_text(DUMMY_TOKEN)
    (auth_dir / "google_client_secret.json").write_text(DUMMY_CLIENT_SECRET)


def scenario_env(installed: bool) -> dict:
    """Scenario: env mode — explicit SUITEWRIGHT_TOKEN + SUITEWRIGHT_CLIENT_SECRET."""
    with tempfile.TemporaryDirectory(prefix="sw-verify-env-") as tmpdir:
        tmp = Path(tmpdir)
        token_path = tmp / "token.json"
        secret_path = tmp / "secret.json"
        token_path.write_text(DUMMY_TOKEN)
        secret_path.write_text(DUMMY_CLIENT_SECRET)

        env = _clean_env()
        env["SUITEWRIGHT_TOKEN"] = str(token_path)
        env["SUITEWRIGHT_CLIENT_SECRET"] = str(secret_path)
        # Use a non-project cwd to avoid dev-root detection
        env["HOME"] = str(tmp)
        if platform.system() == "Windows":
            env["USERPROFILE"] = str(tmp)

        output = _run_auth_check(env, tmp, installed)
        return {
            "scenario": "env",
            "expected_mode": "env",
            "actual_mode": output.get("mode"),
            "passed": output.get("mode") == "env",
            "output": output,
        }


def scenario_xdg(installed: bool) -> dict:
    """Scenario: xdg mode — XDG_CONFIG_HOME explicitly set with auth files."""
    with tempfile.TemporaryDirectory(prefix="sw-verify-xdg-") as tmpdir:
        tmp = Path(tmpdir)
        xdg_config = tmp / "xdg-config"
        auth_dir = xdg_config / "suitewright" / "auth"
        _populate_auth_dir(auth_dir)

        env = _clean_env()
        env["XDG_CONFIG_HOME"] = str(xdg_config)
        env["HOME"] = str(tmp)
        if platform.system() == "Windows":
            env["USERPROFILE"] = str(tmp)

        output = _run_auth_check(env, tmp, installed)
        return {
            "scenario": "xdg",
            "expected_mode": "xdg",
            "actual_mode": output.get("mode"),
            "passed": output.get("mode") == "xdg",
            "output": output,
        }


def scenario_dev(installed: bool) -> dict:
    """Scenario: dev mode — SUITEWRIGHT_AUTH_DIR explicitly set."""
    with tempfile.TemporaryDirectory(prefix="sw-verify-dev-") as tmpdir:
        tmp = Path(tmpdir)
        auth_dir = tmp / "custom-auth"
        _populate_auth_dir(auth_dir)

        env = _clean_env()
        env["SUITEWRIGHT_AUTH_DIR"] = str(auth_dir)
        env["HOME"] = str(tmp)
        if platform.system() == "Windows":
            env["USERPROFILE"] = str(tmp)

        output = _run_auth_check(env, tmp, installed)
        return {
            "scenario": "dev",
            "expected_mode": "dev",
            "actual_mode": output.get("mode"),
            "passed": output.get("mode") == "dev",
            "output": output,
        }


def scenario_default(installed: bool) -> dict:
    """Scenario: default mode — only ~/.config/suitewright/auth/ populated."""
    with tempfile.TemporaryDirectory(prefix="sw-verify-default-") as tmpdir:
        tmp = Path(tmpdir)
        default_auth = tmp / ".config" / "suitewright" / "auth"
        _populate_auth_dir(default_auth)

        env = _clean_env()
        env["HOME"] = str(tmp)
        if platform.system() == "Windows":
            env["USERPROFILE"] = str(tmp)

        output = _run_auth_check(env, tmp, installed)
        return {
            "scenario": "default",
            "expected_mode": "default",
            "actual_mode": output.get("mode"),
            "passed": output.get("mode") == "default",
            "output": output,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify suitewright install across auth modes")
    parser.add_argument(
        "--installed",
        action="store_true",
        help="Use PATH binary instead of uv run",
    )
    args = parser.parse_args()

    scenarios = [
        ("env", scenario_env),
        ("xdg", scenario_xdg),
        ("dev", scenario_dev),
        ("default", scenario_default),
    ]

    results = []
    all_passed = True

    print("=" * 60)
    print("suitewright install verification")
    print(f"  mode: {'installed (PATH)' if args.installed else 'uv run'}")
    print(f"  os:   {platform.system()} {platform.release()}")
    print("=" * 60)
    print()

    for name, fn in scenarios:
        print(f"[{name}] ", end="", flush=True)
        result = fn(args.installed)
        results.append(result)
        if result["passed"]:
            print(f"PASS (mode={result['actual_mode']})")
        else:
            print(f"FAIL (expected={result['expected_mode']}, got={result['actual_mode']})")
            all_passed = False

    # Write JSON report
    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    os_name = platform.system().lower()
    report_name = f"install-verify-{os_name}-{ts}.json"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RUNS_DIR / report_name

    report = {
        "timestamp": ts,
        "os": platform.system(),
        "os_release": platform.release(),
        "python": platform.python_version(),
        "mode": "installed" if args.installed else "uv_run",
        "scenarios": results,
        "all_passed": all_passed,
    }
    report_path.write_text(json.dumps(report, indent=2))
    print()
    print(f"Report: {report_path}")

    # Summary
    print()
    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    if all_passed:
        print(f"All {total} scenarios passed.")
    else:
        print(f"{passed_count}/{total} scenarios passed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
