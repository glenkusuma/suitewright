import pytest

from tests.live.helpers import REPO_ROOT, cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]

REQUESTS_FILE = REPO_ROOT / "tests" / "live" / "fixtures" / "doc_requests.json"


@pytest.fixture
def fresh_doc(sandbox):
    """Create a Doc inside the sandbox folder. Returns the documentId."""
    title = sandbox.name("doc")
    created = cli_run(["docs", "create", "--title", title, "--body", "seed line\n"])
    doc_id = created["documentId"]
    sandbox.track("drive", doc_id)

    # Move into sandbox folder via Drive (CLI has no docs move).
    from suitewright._core.service import build_service

    drive = build_service("drive", "v3")
    drive.files().update(
        fileId=doc_id,
        addParents=sandbox.folder_id,
        removeParents="root",
        fields="id, parents",
    ).execute()
    return doc_id


def _doc_text(doc_id: str) -> str:
    cli_run(["docs", "cache", "fetch", doc_id])
    return cli_run(["docs", "query", "get", doc_id], expect_json=False)


def test_docs_create_with_seed(sandbox):
    title = sandbox.name("seed")
    result = cli_run(["docs", "create", "--title", title, "--body", "hello\n"])
    assert result["status"] == "created"
    assert result["title"] == title
    assert result["characters"] == len("hello\n")
    sandbox.track("drive", result["documentId"])


def test_docs_append(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    result = cli_run(["docs", "mutate", "append", fresh_doc, "--text", "appended-marker"])
    assert result["status"] == "appended"
    text = _doc_text(fresh_doc)
    assert "appended-marker" in text


def test_docs_replace_overwrites_body(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    cli_run(["docs", "mutate", "replace", fresh_doc, "--text", "REPLACED-BODY-MARKER"])
    text = _doc_text(fresh_doc)
    assert "REPLACED-BODY-MARKER" in text
    assert "seed line" not in text


def test_docs_replace_all_finds_and_replaces(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    cli_run(["docs", "mutate", "append", fresh_doc, "--text", "FIND-ME plus FIND-ME again"])
    result = cli_run(
        [
            "docs",
            "mutate",
            "replace-all",
            fresh_doc,
            "--find",
            "FIND-ME",
            "--replace",
            "REWRITTEN",
        ]
    )
    assert result["status"] == "replaced"
    assert result["occurrencesChanged"] >= 2
    assert "FIND-ME" not in _doc_text(fresh_doc)


def test_docs_insert_table_appears_in_structure(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    result = cli_run(
        [
            "docs",
            "mutate",
            "insert-table",
            fresh_doc,
            "--rows",
            "2",
            "--cols",
            "2",
            "--index",
            "1",
        ]
    )
    assert result["status"] == "inserted"
    assert result["requestKind"] == "insertTable"
    cli_run(["docs", "cache", "fetch", fresh_doc])
    structure = cli_run(["docs", "query", "structure", fresh_doc])
    table_blocks = [b for b in structure["blocks"] if b["kind"] == "table"]
    assert len(table_blocks) >= 1


def test_docs_insert_image_inline(sandbox, fresh_doc):
    uri = "https://www.gstatic.com/images/branding/product/1x/docs_2020q4_48dp.png"
    cli_run(["docs", "cache", "fetch", fresh_doc])
    result = cli_run(
        [
            "docs",
            "mutate",
            "insert-image",
            fresh_doc,
            "--uri",
            uri,
            "--index",
            "1",
        ]
    )
    assert result["status"] == "inserted"
    assert result["uri"] == uri


def test_docs_style_range_applies_bold(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    cli_run(["docs", "mutate", "append", fresh_doc, "--text", "STYLE-ME-BOLD"])
    result = cli_run(
        [
            "docs",
            "mutate",
            "style-range",
            fresh_doc,
            "--start-index",
            "1",
            "--end-index",
            "14",
            "--bold",
        ]
    )
    assert result["status"] == "styled"
    assert result["fields"] == "bold"


def test_docs_table_get_after_insert(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    cli_run(
        [
            "docs",
            "mutate",
            "insert-table",
            fresh_doc,
            "--rows",
            "2",
            "--cols",
            "2",
            "--index",
            "1",
        ]
    )
    cli_run(["docs", "cache", "fetch", fresh_doc])
    all_tables = cli_run(["docs", "table", "get", fresh_doc])
    assert isinstance(all_tables["tables"], list)
    assert all_tables["tables"], "expected at least one table after insert"
    one = cli_run(["docs", "table", "get", fresh_doc, "--table", "0"])
    assert one["table"]["tableIndex"] == 0


def test_docs_table_update_cell(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    cli_run(
        [
            "docs",
            "mutate",
            "insert-table",
            fresh_doc,
            "--rows",
            "2",
            "--cols",
            "2",
            "--index",
            "1",
        ]
    )
    result = cli_run(
        [
            "docs",
            "mutate",
            "table-update-cell",
            fresh_doc,
            "--table",
            "0",
            "--row",
            "0",
            "--col",
            "0",
            "--text",
            "CELL-MARKER",
        ]
    )
    assert result["status"] == "updated"
    cli_run(["docs", "cache", "fetch", fresh_doc])
    after = cli_run(["docs", "table", "get", fresh_doc, "--table", "0"])
    assert "CELL-MARKER" in after["table"]["cells"][0][0]


def test_docs_table_append_row(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    cli_run(
        [
            "docs",
            "mutate",
            "insert-table",
            fresh_doc,
            "--rows",
            "1",
            "--cols",
            "2",
            "--index",
            "1",
        ]
    )
    cli_run(["docs", "cache", "fetch", fresh_doc])
    before = cli_run(["docs", "table", "get", fresh_doc, "--table", "0"])
    initial_rows = before["table"]["rows"]
    result = cli_run(
        [
            "docs",
            "mutate",
            "table-append-row",
            fresh_doc,
            "--table",
            "0",
            "--values",
            '["a", "b"]',
        ]
    )
    assert result["status"] == "appended"
    cli_run(["docs", "cache", "fetch", fresh_doc])
    after = cli_run(["docs", "table", "get", fresh_doc, "--table", "0"])
    assert after["table"]["rows"] == initial_rows + 1


def test_docs_update_dry_run_does_not_mutate(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    before = _doc_text(fresh_doc)
    result = cli_run(
        [
            "docs",
            "cache",
            "update",
            fresh_doc,
            str(REQUESTS_FILE),
            "--dry-run",
        ]
    )
    assert result["status"] == "dry-run"
    assert result["requestCount"] == 2
    assert _doc_text(fresh_doc) == before


def test_docs_update_applies(sandbox, fresh_doc):
    cli_run(["docs", "cache", "fetch", fresh_doc])
    result = cli_run(
        [
            "docs",
            "cache",
            "update",
            fresh_doc,
            str(REQUESTS_FILE),
        ]
    )
    assert result.get("documentId") == fresh_doc
    assert "FIXTURE-INSERTED-LINE" in _doc_text(fresh_doc)


def test_docs_plan_emits_artifact(sandbox, fresh_doc):
    plan = cli_run(
        [
            "docs",
            "plan",
            fresh_doc,
            "--requests-file",
            str(REQUESTS_FILE),
        ]
    )
    assert plan["version"] == "1"
    assert plan["documentId"] == fresh_doc
    assert plan["summary"]["requestCount"] == 2
    assert plan["summary"]["requestKinds"] == ["insertText", "updateTextStyle"]


def test_docs_comments_list(sandbox, fresh_doc):
    result = cli_run(["docs", "comments", "list", fresh_doc])
    # returns {"comments": [...], "documentId": "..."} not a bare list
    assert isinstance(result, dict)
    assert "comments" in result
    assert isinstance(result["comments"], list)
