import json

import pytest

from tests.live.helpers import REPO_ROOT, cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]

REQUESTS_FILE = REPO_ROOT / "tests" / "live" / "fixtures" / "form_requests.json"


@pytest.fixture
def fresh_form(sandbox):
    """Create a Form, move it into the sandbox folder, and seed two questions
    via cache-update. Yields a dict with `form_id`, `item_ids` (list of two).
    """
    title = sandbox.name("form")
    created = cli_run(["forms", "create", "--title", title])
    form_id = created["formId"]
    sandbox.track("drive", form_id)

    # Move into sandbox folder via Drive API (CLI has no forms move).
    from suitewright.service import build_service

    drive = build_service("drive", "v3")
    drive.files().update(
        fileId=form_id,
        addParents=sandbox.folder_id,
        removeParents="root",
        fields="id, parents",
    ).execute()

    # Fetch + seed two questions
    cli_run(["forms", "fetch", form_id], expect_json=False)
    cli_run(
        [
            "forms",
            "cache-update",
            form_id,
            str(REQUESTS_FILE),
            "--include-form-in-response",
        ],
        expect_json=False,
    )

    # Re-fetch and read the cache to capture itemIds
    cli_run(["forms", "fetch", form_id], expect_json=False)
    cache_path_str = cli_run(["forms", "show-cache", form_id], expect_json=False).strip()
    payload = json.loads(open(cache_path_str).read())
    item_ids = [it["itemId"] for it in payload.get("items", [])]

    return {"form_id": form_id, "item_ids": item_ids}


def test_forms_create_returns_id(sandbox):
    title = sandbox.name("createonly")
    result = cli_run(["forms", "create", "--title", title])
    assert "formId" in result
    sandbox.track("drive", result["formId"])


def test_forms_fetch_writes_cache(sandbox, fresh_form):
    out = cli_run(["forms", "show-cache", fresh_form["form_id"]], expect_json=False)
    assert out.strip()


def test_forms_validate_reports_ok(sandbox, fresh_form):
    result = cli_run(["forms", "validate", fresh_form["form_id"], "--verbose"])
    assert result["status"] == "ok"
    assert result["formId"] == fresh_form["form_id"]
    assert "revisionId" in result


def test_forms_update_noop_batch(sandbox, fresh_form):
    # The Forms API rejects an empty batch - send a no-op updateSettings instead.
    result = cli_run(
        [
            "forms",
            "update",
            fresh_form["form_id"],
            "--requests",
            '[{"updateSettings": {"settings": {"quizSettings": {"isQuiz": false}},'
            ' "updateMask": "quizSettings.isQuiz"}}]',
        ]
    )
    # batchUpdate response is {"replies": [...], "writeControl": {...}} - no formId
    assert "writeControl" in result or "replies" in result


def test_forms_query_locate_by_title(sandbox, fresh_form):
    result = cli_run(
        [
            "forms",
            "query",
            "locate",
            fresh_form["form_id"],
            "--title",
            "Question 1",
        ]
    )
    # locate returns {"index": N}
    assert "index" in result
    assert isinstance(result["index"], int)


def test_forms_query_locate_by_item_id(sandbox, fresh_form):
    if not fresh_form["item_ids"]:
        pytest.skip("no items seeded")
    target = fresh_form["item_ids"][0]
    result = cli_run(
        [
            "forms",
            "query",
            "locate",
            fresh_form["form_id"],
            "--item-id",
            target,
        ]
    )
    # locate returns {"index": N}
    assert "index" in result
    assert isinstance(result["index"], int)


def test_forms_query_after(sandbox, fresh_form):
    result = cli_run(
        [
            "forms",
            "query",
            "after",
            fresh_form["form_id"],
            "--title",
            "Question 1",
        ]
    )
    # after returns {"afterIndex": N}
    assert "afterIndex" in result
    assert result["afterIndex"] >= 1


def test_forms_query_delete_request(sandbox, fresh_form):
    if len(fresh_form["item_ids"]) < 2:
        pytest.skip("need at least 2 items")
    target = fresh_form["item_ids"][1]
    result = cli_run(
        [
            "forms",
            "query",
            "delete-request",
            fresh_form["form_id"],
            "--item-id",
            target,
        ]
    )
    requests = result if isinstance(result, list) else [result]
    update = cli_run(
        [
            "forms",
            "update",
            fresh_form["form_id"],
            "--requests",
            json.dumps(requests),
        ]
    )
    # batchUpdate response is {"replies": [...], "writeControl": {...}}
    assert "writeControl" in update or "replies" in update


def test_forms_query_get_item(sandbox, fresh_form):
    if not fresh_form["item_ids"]:
        pytest.skip("no items seeded")
    target = fresh_form["item_ids"][0]
    item = cli_run(
        [
            "forms",
            "query",
            "get-item",
            fresh_form["form_id"],
            "--item-id",
            target,
        ]
    )
    assert item["itemId"] == target
    assert item["title"] == "Question 1"


def test_forms_query_neighbors(sandbox, fresh_form):
    result = cli_run(
        [
            "forms",
            "query",
            "neighbors",
            fresh_form["form_id"],
            "--title",
            "Question 1",
            "--before",
            "1",
            "--after",
            "1",
        ]
    )
    # neighbors returns a list of compact item dicts
    assert isinstance(result, list)


def test_forms_query_indexer_default_pattern(sandbox, fresh_form):
    result = cli_run(
        [
            "forms",
            "query",
            "indexer",
            fresh_form["form_id"],
        ]
    )
    assert isinstance(result, (dict, list))


def test_forms_query_indexer_custom_pattern(sandbox, fresh_form):
    result = cli_run(
        [
            "forms",
            "query",
            "indexer",
            fresh_form["form_id"],
            "--pattern",
            r"^Question \d+",
        ]
    )
    items = result if isinstance(result, list) else result.get("matches", [])
    assert len(items) >= 1
