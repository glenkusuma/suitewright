from pathlib import Path

import pytest

from tests.live.helpers import REPO_ROOT, cli_run

pytestmark = [pytest.mark.live, pytest.mark.destructive]

PAYLOAD = REPO_ROOT / "tests" / "live" / "fixtures" / "upload_payload.txt"


def test_drive_share_round_trip(sandbox):
    if not sandbox.self_email:
        pytest.skip("self_email not resolved; set SUITEWRIGHT_LIVE_TEST_EMAIL")

    expected = PAYLOAD.read_bytes()

    # 1. Upload into sandbox.
    upload = cli_run(
        [
            "drive",
            "upload",
            str(PAYLOAD),
            "--name",
            sandbox.name("share-rt"),
            "--parent",
            sandbox.folder_id,
        ]
    )
    file_id = upload["id"]

    # 2. Share with commenter role.
    share = cli_run(
        [
            "drive",
            "share",
            file_id,
            "--email",
            sandbox.self_email,
            "--role",
            "commenter",
        ]
    )
    assert share["status"] == "shared"
    assert share["role"] == "commenter"

    # 3. Download and compare bytes.
    out_path = sandbox.artifacts / "downloads" / f"{file_id}.bin"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    download = cli_run(
        [
            "drive",
            "download",
            file_id,
            "--output",
            str(out_path),
        ]
    )
    assert download["status"] == "downloaded"
    assert Path(download["path"]).read_bytes() == expected

    # 4. Permanent delete.
    deleted = cli_run(["drive", "delete", file_id, "--permanent"])
    assert deleted["status"] == "deleted"
    assert deleted["permanent"] is True

    # 5. Subsequent get must 404.
    proc = cli_run(
        ["drive", "get", file_id],
        allow_nonzero=True,
        expect_json=False,
    )
    assert proc.returncode != 0
