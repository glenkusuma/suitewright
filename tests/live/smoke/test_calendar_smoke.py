import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.smoke]


def test_calendar_list_returns_array(sandbox):
    events = cli_run(
        [
            "calendar",
            "list",
            "--calendar",
            sandbox.calendar_id,
            "--max",
            "5",
        ]
    )
    assert isinstance(events, list)
