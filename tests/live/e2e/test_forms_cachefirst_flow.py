import json

import pytest

from tests.live.helpers import REPO_ROOT, cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]

INSERT_FIXTURE = REPO_ROOT / "tests" / "live" / "fixtures" / "form_requests.json"


def test_forms_cachefirst_flow(sandbox, tmp_path):
    # 1. Create form.
    title = sandbox.name("cachefirst")
    created = cli_run(["forms", "create", "--title", title])
    form_id = created["formId"]
    sandbox.track("drive", form_id)

    # 2. Move into sandbox folder.
    from suitewright.service import build_service

    drive = build_service("drive", "v3")
    drive.files().update(
        fileId=form_id,
        addParents=sandbox.folder_id,
        removeParents="root",
        fields="id, parents",
    ).execute()

    # 3. Initial fetch + validate.
    cli_run(["forms", "fetch", form_id], expect_json=False)
    initial = cli_run(["forms", "validate", form_id, "--verbose"])
    assert initial["status"] == "ok"

    # 4. Cache-update with insert fixture (adds Question 1 + Question 2).
    cli_run(
        [
            "forms",
            "cache-update",
            form_id,
            str(INSERT_FIXTURE),
        ],
        expect_json=False,
    )

    # 5. Refresh + locate Question 1 by title — returns {"index": N}
    cli_run(["forms", "fetch", form_id], expect_json=False)
    locate = cli_run(
        [
            "forms",
            "query",
            "locate",
            form_id,
            "--title",
            "Question 1",
        ]
    )
    # Use get-item to resolve the itemId from the cache
    cache_path_str = cli_run(["forms", "show-cache", form_id], expect_json=False).strip()
    import json as _json

    cache_items = _json.loads(open(cache_path_str).read()).get("items", [])
    target_item_id = cache_items[locate["index"]]["itemId"]

    # 6. Build a delete request via the CLI helper.
    delete_payload = cli_run(
        [
            "forms",
            "query",
            "delete-request",
            form_id,
            "--item-id",
            target_item_id,
        ]
    )
    delete_requests = delete_payload if isinstance(delete_payload, list) else [delete_payload]
    delete_file = tmp_path / "delete.json"
    delete_file.write_text(json.dumps(delete_requests))

    # 7. Apply the delete via cache-update.
    cli_run(
        [
            "forms",
            "cache-update",
            form_id,
            str(delete_file),
        ],
        expect_json=False,
    )

    # 8. Final validate — cache is fresh.
    final = cli_run(["forms", "validate", form_id, "--verbose"])
    assert final["status"] == "ok"

    # 9. Confirm Question 1 is gone.
    proc = cli_run(
        ["forms", "query", "locate", form_id, "--title", "Question 1"],
        allow_nonzero=True,
        expect_json=False,
    )
    assert proc.returncode != 0
