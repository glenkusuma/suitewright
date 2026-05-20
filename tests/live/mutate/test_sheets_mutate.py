import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]


@pytest.fixture
def sheet(sandbox):
    """Create a Google Sheet inside the sandbox folder via the Drive API.
    The Sheets CLI does not expose `create`; this is test infrastructure.
    """
    from suitewright.service import build_service

    drive = build_service("drive", "v3")
    name = sandbox.name("sheet")
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [sandbox.folder_id],
    }
    created = drive.files().create(body=body, fields="id").execute()
    sheet_id = created["id"]
    sandbox.track("drive", sheet_id)
    return sheet_id


def test_sheets_append_then_get(sandbox, sheet):
    append = cli_run(
        [
            "sheets",
            "append",
            sheet,
            "Sheet1!A1",
            "--values",
            '[["alpha", "beta"]]',
        ]
    )
    assert append["updatedCells"] >= 2

    rows = cli_run(["sheets", "get", sheet, "Sheet1!A1:B1"])
    assert rows == [["alpha", "beta"]]


def test_sheets_update_overwrites(sandbox, sheet):
    cli_run(
        [
            "sheets",
            "append",
            sheet,
            "Sheet1!A1",
            "--values",
            '[["seed", "row"]]',
        ]
    )
    update = cli_run(
        [
            "sheets",
            "update",
            sheet,
            "Sheet1!A1:B1",
            "--values",
            '[["x", "y"]]',
        ]
    )
    assert update["updatedCells"] == 2

    rows = cli_run(["sheets", "get", sheet, "Sheet1!A1:B1"])
    assert rows == [["x", "y"]]
