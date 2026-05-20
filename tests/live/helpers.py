"""Helpers for live CLI tests.

Everything here is exercised against the user's real Google account when the
suite is run with `--run-live`. Keep imports stdlib-only — no python-dotenv,
no third-party deps.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_ENV_PATH = REPO_ROOT / ".env"
ARTIFACTS_ROOT = REPO_ROOT / "_local" / "tests" / "live" / ".runs"


def parse_dotenv(path: Path) -> dict[str, str]:
    """Tiny .env parser. Supports KEY=VALUE, # comments, blank lines, single/double quotes.
    Does NOT support multi-line values, variable expansion, or `export` prefixes.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        out[key] = value
    return out


def load_live_env() -> dict[str, str]:
    """Load .env into os.environ (without overriding values already set)."""
    if not LIVE_ENV_PATH.exists():
        raise RuntimeError(".env not found. Run: uv run python tests/live/scripts/bootstrap.py")
    parsed = parse_dotenv(LIVE_ENV_PATH)
    for key, value in parsed.items():
        if value and key not in os.environ:
            os.environ[key] = value
    return parsed


def cli_run(
    args: list[str],
    *,
    expect_json: bool = True,
    allow_nonzero: bool = False,
    timeout: int = 60,
    stdin: str | None = None,
) -> Any:
    """Run `uv run suitewright <args>` and return parsed JSON (or raw stdout).

    Raises AssertionError on non-zero exit unless allow_nonzero=True; in that
    case returns a CompletedProcess so the caller can inspect returncode/stderr.
    """
    cmd = ["uv", "run", "suitewright", *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=REPO_ROOT,
        input=stdin,
    )
    if not allow_nonzero and proc.returncode != 0:
        raise AssertionError(
            f"CLI failed: {' '.join(cmd)}\n"
            f"  exit={proc.returncode}\n"
            f"  stderr={proc.stderr.strip()}\n"
            f"  stdout={proc.stdout.strip()}"
        )
    if allow_nonzero and proc.returncode != 0:
        return proc
    if not expect_json or not proc.stdout.strip():
        return proc.stdout
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"CLI returned non-JSON stdout: {' '.join(cmd)}\n"
            f"  error={exc}\n"
            f"  stdout={proc.stdout[:500]}"
        ) from exc


def short_uuid(n: int = 6) -> str:
    return uuid.uuid4().hex[:n]


def make_run_id() -> str:
    import datetime as dt

    return dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + short_uuid(4)


def artifacts_dir(run_id: str) -> Path:
    p = ARTIFACTS_ROOT / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p
