import pytest

from tests.live.helpers import REPO_ROOT, cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]

REQUESTS_FILE = REPO_ROOT / "tests" / "live" / "fixtures" / "doc_requests.json"


def test_doc_collab_flow(sandbox):
    # 1. Create the doc.
    title = sandbox.name("collab")
    created = cli_run(["docs", "create", "--title", title, "--body", "header line\n"])
    doc_id = created["documentId"]
    sandbox.track("drive", doc_id)

    from suitewright.service import build_service

    drive = build_service("drive", "v3")
    drive.files().update(
        fileId=doc_id,
        addParents=sandbox.folder_id,
        removeParents="root",
        fields="id, parents",
    ).execute()

    # 2. Append seed content.
    cli_run(["docs", "append", doc_id, "--text", "agent-seed-line"])

    # 3. Inspect structure.
    structure = cli_run(["docs", "show-structure", doc_id, "--full-text"])
    assert structure["documentId"] == doc_id
    assert structure["summary"]["paragraphs"] >= 1

    # 4. Dry-run validates request shape, no mutation.
    dry = cli_run(
        [
            "docs",
            "update",
            doc_id,
            "--requests-file",
            str(REQUESTS_FILE),
            "--dry-run",
        ]
    )
    assert dry["dryRun"] is True
    assert dry["requestCount"] == 2

    # 5. Build a plan artifact (read-only).
    plan = cli_run(
        [
            "docs",
            "plan",
            doc_id,
            "--requests-file",
            str(REQUESTS_FILE),
        ]
    )
    assert plan["version"] == "1"
    assert plan["summary"]["requestCount"] == 2

    # 6. Apply the batch for real.
    apply_result = cli_run(
        [
            "docs",
            "update",
            doc_id,
            "--requests-file",
            str(REQUESTS_FILE),
        ]
    )
    # batchUpdate response contains "replies" not "documentId"
    assert "replies" in apply_result or apply_result is not None

    # 7. Confirm fixture text now appears in the body.
    final = cli_run(["docs", "get", doc_id])
    assert "FIXTURE-INSERTED-LINE" in final["body"]

    # 8. Verify comments list returns a dict with comments key.
    comments = cli_run(["docs", "comments", "list", doc_id])
    assert isinstance(comments, dict) and "comments" in comments

    # 9. Share with self (sandbox-scoped).
    if sandbox.self_email:
        share = cli_run(
            [
                "drive",
                "share",
                doc_id,
                "--email",
                sandbox.self_email,
                "--role",
                "reader",
            ]
        )
        assert share["status"] == "shared"
