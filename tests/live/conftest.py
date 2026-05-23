"""Live test fixtures and opt-in gating.

Run shape:
    uv run pytest tests/live/ -m smoke --run-live
    uv run pytest tests/live/ --run-live

Without --run-live every item in tests/live/ is skipped at collection time.

IMPORTANT:
- Live tests are excluded from the default `uv run pytest` run (via --ignore in
  pyproject.toml). They only run when explicitly targeted.
- Live tests CANNOT run in parallel. pytest-xdist is disabled for this directory.
- Smoke, mutate, and destructive tiers run sequentially (ordered by risk level).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from filelock import FileLock, Timeout

from .helpers import (
    artifacts_dir,
    cli_run,
    load_live_env,
    make_run_id,
    short_uuid,
)

# ---- filelock enforcement -----------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCK_PATH = _REPO_ROOT / "_local" / "tests" / "live" / ".runs" / "live-account.lock"
_session_lock: FileLock | None = None

# ---- opt-in flag --------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live tests under tests/live/ against a real Google account.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        # Enforce sequential ordering: smoke → mutate → destructive → e2e
        tier_order = {"smoke": 0, "mutate": 1, "destructive": 2}

        def _sort_key(item):
            for marker, order in tier_order.items():
                if marker in item.keywords:
                    return order
            return 3  # e2e and unmarked go last

        items[:] = sorted(items, key=_sort_key)
        return

    skip = pytest.mark.skip(reason="needs --run-live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


# ---- disable parallel execution (pytest-xdist) --------------------------------

# If pytest-xdist is installed, force live tests to run on a single worker.
# This file is only loaded when tests/live/ is explicitly targeted.


def pytest_configure(config):
    """Disable pytest-xdist parallelism for live tests."""
    # Override -n/--numprocesses if xdist is active
    if hasattr(config, "workerinput"):
        # We're already in a worker — nothing to do
        return
    try:
        worker_count = config.getoption("numprocesses", default=None)
    except (ValueError, AttributeError):
        worker_count = None
    if worker_count is not None and worker_count != 0:
        config.option.numprocesses = 0
        config.option.dist = "no"


# ---- filelock session fixture -------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _live_account_lock(request) -> Iterator[None]:
    """Acquire an exclusive filelock so only one live session runs at a time."""
    global _session_lock

    if not request.config.getoption("--run-live"):
        yield
        return

    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _session_lock = FileLock(_LOCK_PATH, timeout=1)

    try:
        _session_lock.acquire()
    except Timeout:
        pytest.exit(
            "Another live test session is already running (could not acquire "
            f"{_LOCK_PATH}). Wait for it to finish or remove the stale lock file.",
            returncode=3,
        )

    yield

    _session_lock.release()


# ---- sandbox dataclass --------------------------------------------------------


@dataclass
class Sandbox:
    run_id: str
    folder_id: str
    label_id: str
    label_name: str
    calendar_id: str
    self_email: str
    prefix: str
    artifacts: Path
    created: list[tuple[str, str]] = field(default_factory=list)

    def track(self, kind: str, resource_id: str) -> None:
        """Record a resource for teardown. kind ∈ {drive, gmail_msg, calendar_event}."""
        self.created.append((kind, resource_id))

    def name(self, suffix: str) -> str:
        return f"{self.prefix}-{suffix}-{short_uuid()}"


# ---- sandbox fixture ----------------------------------------------------------


@pytest.fixture(scope="session")
def sandbox(request) -> Iterator[Sandbox]:
    if not request.config.getoption("--run-live"):
        pytest.skip("needs --run-live")

    load_live_env()

    # auth check — abort cleanly if not authenticated
    proc = cli_run(["auth", "check"], allow_nonzero=True, expect_json=False)
    if hasattr(proc, "returncode") and proc.returncode != 0:
        pytest.exit(
            "live tests require a valid token. Run: uv run python tests/live/scripts/bootstrap.py",
            returncode=2,
        )

    prefix = os.environ.get("SUITEWRIGHT_LIVE_TEST_PREFIX", "suitewright-live-test")
    calendar_id = os.environ.get("SUITEWRIGHT_LIVE_TEST_CALENDAR_ID", "primary")
    self_email = os.environ.get("SUITEWRIGHT_LIVE_TEST_EMAIL", "")
    root_folder_id = os.environ.get("SUITEWRIGHT_LIVE_TEST_ROOT_FOLDER_ID", "")

    run_id = make_run_id()
    artifacts = artifacts_dir(run_id)

    # sandbox Drive folder — nested inside root folder if configured
    folder_name = f"{prefix}-{run_id}"
    folder_cmd = ["drive", "create-folder", folder_name]
    if root_folder_id:
        folder_cmd += ["--parent", root_folder_id]
    folder = cli_run(folder_cmd)
    folder_id = folder["id"]

    # sandbox Gmail label (idempotent)
    label_id, label_name = _ensure_label(prefix)

    # self-email fallback: derive from sent mail if not set in .env
    if not self_email:
        raw = cli_run(
            ["gmail", "search", "in:sent", "--max", "1"],
            expect_json=False,
            allow_nonzero=True,
        )
        stdout = raw if isinstance(raw, str) else getattr(raw, "stdout", "")
        try:
            import json as _json

            msgs = _json.loads(stdout)
            if isinstance(msgs, list) and msgs:
                full = cli_run(["gmail", "get", msgs[0]["id"]])
                for header in full.get("payload", {}).get("headers", []):
                    if header.get("name", "").lower() == "from":
                        self_email = _extract_email(header.get("value", ""))
                        break
        except Exception:
            pass

    sb = Sandbox(
        run_id=run_id,
        folder_id=folder_id,
        label_id=label_id,
        label_name=label_name,
        calendar_id=calendar_id,
        self_email=self_email,
        prefix=prefix,
        artifacts=artifacts,
    )

    yield sb

    _teardown(sb)


def _ensure_label(prefix: str) -> tuple[str, str]:
    name = prefix
    labels = cli_run(["gmail", "labels"])
    for label in labels:
        if label.get("name") == name:
            return label["id"], name
    # CLI has no gmail labels create — use the API directly (test infra only).
    from suitewright._core.service import build_service

    svc = build_service("gmail", "v1")
    created = (
        svc.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    return created["id"], name


def _extract_email(header_value: str) -> str:
    if "<" in header_value and ">" in header_value:
        return header_value.split("<", 1)[1].split(">", 1)[0]
    return header_value.strip()


def _teardown(sb: Sandbox) -> None:
    cleanup = []
    leaked = []
    for kind, rid in reversed(sb.created):
        try:
            if kind == "drive":
                cli_run(
                    ["drive", "delete", rid, "--permanent"],
                    expect_json=False,
                    allow_nonzero=True,
                )
            elif kind == "gmail_msg":
                cli_run(["gmail", "trash", rid], expect_json=False, allow_nonzero=True)
            elif kind == "calendar_event":
                cli_run(
                    ["calendar", "delete", rid, "--calendar", sb.calendar_id],
                    expect_json=False,
                    allow_nonzero=True,
                )
            cleanup.append({"kind": kind, "id": rid, "ok": True})
        except Exception as exc:
            cleanup.append({"kind": kind, "id": rid, "ok": False, "error": str(exc)})
            leaked.append({"kind": kind, "id": rid})

    # Permanently delete the sandbox folder last.
    try:
        cli_run(
            ["drive", "delete", sb.folder_id, "--permanent"],
            expect_json=False,
            allow_nonzero=True,
        )
        cleanup.append({"kind": "sandbox_folder", "id": sb.folder_id, "ok": True})
    except Exception as exc:
        cleanup.append(
            {"kind": "sandbox_folder", "id": sb.folder_id, "ok": False, "error": str(exc)}
        )
        leaked.append({"kind": "drive", "id": sb.folder_id})

    (sb.artifacts / "cleanup.json").write_text(json.dumps(cleanup, indent=2))
    if leaked:
        (sb.artifacts / "leaked.json").write_text(json.dumps(leaked, indent=2))


# ---- marker enforcement -------------------------------------------------------


@pytest.hookimpl(tryfirst=True)
def pytest_collection_finish(session):
    """Refuse to run a destructive/mutate test that is not also marked live."""
    bad = []
    for item in session.items:
        keywords = set(item.keywords)
        if "destructive" in keywords and "live" not in keywords:
            bad.append(item.nodeid)
        if "mutate" in keywords and "live" not in keywords:
            bad.append(item.nodeid)
    if bad:
        raise pytest.UsageError(
            "destructive/mutate tests must also carry @pytest.mark.live:\n  - " + "\n  - ".join(bad)
        )
