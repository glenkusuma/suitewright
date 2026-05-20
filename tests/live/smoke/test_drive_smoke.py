import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.smoke]


def test_drive_search_returns_array(sandbox):
    result = cli_run(["drive", "search", "", "--max", "5"])
    assert isinstance(result, list)


def test_drive_get_sandbox_folder(sandbox):
    folder = cli_run(["drive", "get", sandbox.folder_id])
    assert folder["id"] == sandbox.folder_id
    assert folder.get("mimeType") == "application/vnd.google-apps.folder"
