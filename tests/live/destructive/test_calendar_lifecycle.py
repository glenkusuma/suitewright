from datetime import UTC, datetime, timedelta

import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.destructive]


def test_calendar_create_list_delete(sandbox):
    start = datetime.now(UTC) + timedelta(days=1)
    end = start + timedelta(minutes=30)
    summary = f"[{sandbox.prefix}] {sandbox.run_id} event"

    created = cli_run(
        [
            "calendar",
            "create",
            "--calendar",
            sandbox.calendar_id,
            "--summary",
            summary,
            "--start",
            start.isoformat(),
            "--end",
            end.isoformat(),
        ]
    )
    assert created["status"] == "created"
    event_id = created["id"]
    sandbox.track("calendar_event", event_id)

    listing = cli_run(
        [
            "calendar",
            "list",
            "--calendar",
            sandbox.calendar_id,
            "--start",
            start.isoformat(),
            "--end",
            (end + timedelta(minutes=1)).isoformat(),
            "--max",
            "10",
        ]
    )
    assert any(e["id"] == event_id for e in listing)

    deleted = cli_run(
        [
            "calendar",
            "delete",
            event_id,
            "--calendar",
            sandbox.calendar_id,
        ]
    )
    assert deleted["status"] == "deleted"
