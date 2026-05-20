from pathlib import Path

import pytest

from tests.live.helpers import REPO_ROOT, cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]

PAYLOAD = REPO_ROOT / "tests" / "live" / "fixtures" / "upload_payload.txt"


def test_create_folder_inside_sandbox(sandbox):
    name = sandbox.name("subfolder")
    result = cli_run(["drive", "create-folder", name, "--parent", sandbox.folder_id])
    assert result["status"] == "created"
    sandbox.track("drive", result["id"])
    folder = cli_run(["drive", "get", result["id"]])
    assert folder["mimeType"] == "application/vnd.google-apps.folder"
    assert sandbox.folder_id in folder.get("parents", [])


def test_upload_download_round_trip(sandbox):
    expected = PAYLOAD.read_bytes()
    upload = cli_run(
        [
            "drive",
            "upload",
            str(PAYLOAD),
            "--name",
            sandbox.name("upload"),
            "--parent",
            sandbox.folder_id,
        ]
    )
    assert upload["status"] == "uploaded"
    sandbox.track("drive", upload["id"])

    out_path = sandbox.artifacts / "downloads" / f"{upload['id']}.bin"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    download = cli_run(
        [
            "drive",
            "download",
            upload["id"],
            "--output",
            str(out_path),
        ]
    )
    assert download["status"] == "downloaded"
    assert Path(download["path"]).read_bytes() == expected


def test_share_grants_permission(sandbox):
    if not sandbox.self_email:
        pytest.skip("self_email not resolved; set SUITEWRIGHT_LIVE_TEST_EMAIL")
    upload = cli_run(
        [
            "drive",
            "upload",
            str(PAYLOAD),
            "--name",
            sandbox.name("share"),
            "--parent",
            sandbox.folder_id,
        ]
    )
    sandbox.track("drive", upload["id"])
    result = cli_run(
        [
            "drive",
            "share",
            upload["id"],
            "--email",
            sandbox.self_email,
            "--role",
            "reader",
        ]
    )
    assert result["status"] == "shared"
    assert result["fileId"] == upload["id"]
    assert result["role"] == "reader"
