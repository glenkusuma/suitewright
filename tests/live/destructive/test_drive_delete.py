import pytest

from tests.live.helpers import REPO_ROOT, cli_run

pytestmark = [pytest.mark.live, pytest.mark.destructive]

PAYLOAD = REPO_ROOT / "tests" / "live" / "fixtures" / "upload_payload.txt"


def test_drive_delete_trash(sandbox):
    upload = cli_run(
        [
            "drive",
            "upload",
            str(PAYLOAD),
            "--name",
            sandbox.name("trash"),
            "--parent",
            sandbox.folder_id,
        ]
    )
    file_id = upload["id"]

    trashed = cli_run(["drive", "delete", file_id])
    assert trashed["status"] == "trashed"
    assert trashed["permanent"] is False

    # File still exists in trash; get returns metadata.
    meta = cli_run(["drive", "get", file_id])
    assert meta["id"] == file_id


def test_drive_delete_permanent(sandbox):
    upload = cli_run(
        [
            "drive",
            "upload",
            str(PAYLOAD),
            "--name",
            sandbox.name("perm"),
            "--parent",
            sandbox.folder_id,
        ]
    )
    file_id = upload["id"]

    deleted = cli_run(["drive", "delete", file_id, "--permanent"])
    assert deleted["status"] == "deleted"
    assert deleted["permanent"] is True

    # Subsequent get must fail (404).
    proc = cli_run(["drive", "get", file_id], allow_nonzero=True, expect_json=False)
    assert proc.returncode != 0
