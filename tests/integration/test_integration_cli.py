"""Integration tests for all suitewright CLI subcommands.

Tests invoke the CLI through build_parser() / main() with mocked Google API
services. No real network calls are made. Each test verifies the full
dispatch path: argparse -> handler -> service call -> stdout JSON.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from suitewright.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(args: list[str], capsys) -> dict | list | str:
    """Run the CLI and return parsed stdout JSON (or raw string)."""
    main(args)
    out = capsys.readouterr().out.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out


def mock_service(methods: dict) -> MagicMock:
    """Build a mock service where each key is a resource method chain."""
    svc = MagicMock()
    for attr_path, return_value in methods.items():
        parts = attr_path.split(".")
        obj = svc
        for part in parts[:-1]:
            obj = getattr(obj, part)()
        leaf = getattr(obj, parts[-1])
        leaf.return_value.execute.return_value = return_value
    return svc


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuthIntegration:
    def test_check_authenticated(self, capsys, tmp_path):
        from suitewright.service import SCOPES

        token = tmp_path / "google_token.json"
        token.write_text(json.dumps({"token": "tok", "refresh_token": "ref", "scopes": SCOPES}))
        mock_creds = MagicMock()
        mock_creds.valid = True
        with patch("suitewright.auth.paths.resolve", return_value=token):
            with patch("suitewright.auth.paths.describe", return_value={}):
                with patch(
                    "google.oauth2.credentials.Credentials.from_authorized_user_file",
                    return_value=mock_creds,
                ):
                    main(["auth", "check"])
        out = capsys.readouterr().out
        assert "AUTHENTICATED" in out

    def test_check_not_authenticated(self, capsys, tmp_path):
        missing = tmp_path / "no_token.json"
        with patch("suitewright.auth.paths.resolve", return_value=missing):
            with patch("suitewright.auth.paths.describe", return_value={}):
                with pytest.raises(SystemExit):
                    main(["auth", "check"])


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------


class TestGmailIntegration:
    def test_search(self, capsys):
        svc = MagicMock()
        svc.users().messages().list().execute.return_value = {"messages": [{"id": "m1"}]}
        detail = {
            "id": "m1",
            "threadId": "t1",
            "snippet": "Hello",
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [
                    {"name": "From", "value": "a@b.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Subject", "value": "Hi"},
                    {"name": "Date", "value": "2025-01-15"},
                ]
            },
        }
        svc.users().messages().get().execute.return_value = detail
        with patch("suitewright.gmail.build_service", return_value=svc):
            result = run(["gmail", "search", "is:unread", "--max", "1"], capsys)
        assert isinstance(result, list)
        assert result[0]["id"] == "m1"

    def test_labels(self, capsys):
        svc = MagicMock()
        svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "INBOX", "name": "INBOX", "type": "system"}]
        }
        with patch("suitewright.gmail.build_service", return_value=svc):
            result = run(["gmail", "labels"], capsys)
        assert isinstance(result, list)
        assert result[0]["id"] == "INBOX"

    def test_trash(self, capsys):
        svc = MagicMock()
        svc.users().messages().trash().execute.return_value = {"id": "m1", "threadId": "t1"}
        with patch("suitewright.gmail.build_service", return_value=svc):
            result = run(["gmail", "trash", "m1"], capsys)
        assert result["status"] == "trashed"


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


class TestCalendarIntegration:
    def test_list(self, capsys):
        events = [
            {
                "id": "e1",
                "summary": "Meeting",
                "start": {"dateTime": "2025-01-15T10:00:00Z"},
                "end": {"dateTime": "2025-01-15T11:00:00Z"},
            }
        ]
        svc = mock_service({"events.list": {"items": events}})
        with patch("suitewright.calendar.build_service", return_value=svc):
            result = run(["calendar", "list", "--calendar", "primary"], capsys)
        assert isinstance(result, list)

    def test_create(self, capsys):
        created = {"id": "e2", "summary": "Standup", "htmlLink": "https://calendar.google.com/e/e2"}
        svc = mock_service({"events.insert": created})
        with patch("suitewright.calendar.build_service", return_value=svc):
            result = run(
                [
                    "calendar",
                    "create",
                    "--summary",
                    "Standup",
                    "--start",
                    "2025-01-15T10:00:00+07:00",
                    "--end",
                    "2025-01-15T10:30:00+07:00",
                    "--calendar",
                    "primary",
                ],
                capsys,
            )
        assert result.get("status") == "created"

    def test_delete(self, capsys):
        svc = MagicMock()
        svc.events().delete().execute.return_value = {}
        with patch("suitewright.calendar.build_service", return_value=svc):
            result = run(["calendar", "delete", "e1", "--calendar", "primary"], capsys)
        assert result.get("status") == "deleted"


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------


class TestDriveIntegration:
    def test_search(self, capsys):
        files = [
            {
                "id": "f1",
                "name": "Report.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2025-01-15",
                "webViewLink": "https://drive.google.com/f1",
            }
        ]
        svc = mock_service({"files.list": {"files": files}})
        with patch("suitewright.drive.build_service", return_value=svc):
            result = run(["drive", "search", "report"], capsys)
        assert isinstance(result, list)
        assert result[0]["id"] == "f1"

    def test_get(self, capsys):
        meta = {
            "id": "f1",
            "name": "Doc.pdf",
            "mimeType": "application/pdf",
            "modifiedTime": "2025-01-15",
            "webViewLink": "https://drive.google.com/f1",
        }
        svc = mock_service({"files.get": meta})
        with patch("suitewright.drive.build_service", return_value=svc):
            result = run(["drive", "get", "f1"], capsys)
        assert result["id"] == "f1"

    def test_delete_trash(self, capsys):
        svc = MagicMock()
        svc.files().update().execute.return_value = {"id": "f1", "trashed": True}
        with patch("suitewright.drive.build_service", return_value=svc):
            result = run(["drive", "delete", "f1"], capsys)
        assert result.get("permanent") is False

    def test_delete_permanent(self, capsys):
        svc = MagicMock()
        svc.files().delete().execute.return_value = {}
        with patch("suitewright.drive.build_service", return_value=svc):
            result = run(["drive", "delete", "f1", "--permanent"], capsys)
        assert result.get("permanent") is True

    def test_create_folder(self, capsys):
        created = {
            "id": "folder1",
            "name": "Reports",
            "webViewLink": "https://drive.google.com/folder1",
        }
        svc = mock_service({"files.create": created})
        with patch("suitewright.drive.build_service", return_value=svc):
            result = run(["drive", "create-folder", "Reports"], capsys)
        assert result.get("status") == "created"

    def test_share(self, capsys):
        perm = {"id": "perm1", "role": "reader", "type": "user"}
        svc = mock_service({"permissions.create": perm})
        with patch("suitewright.drive.build_service", return_value=svc):
            result = run(["drive", "share", "f1", "--email", "a@b.com", "--role", "reader"], capsys)
        assert result.get("status") == "shared"


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


class TestContactsIntegration:
    def test_list(self, capsys):
        people = [
            {
                "names": [{"displayName": "Alice"}],
                "emailAddresses": [{"value": "alice@example.com"}],
            }
        ]
        svc = mock_service({"people.connections.list": {"connections": people}})
        with patch("suitewright.contacts.build_service", return_value=svc):
            result = run(["contacts", "list", "--max", "1"], capsys)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------


class TestSheetsIntegration:
    def test_get(self, capsys):
        svc = mock_service(
            {"spreadsheets.values.get": {"values": [["Name", "Score"], ["Alice", "95"]]}}
        )
        with patch("suitewright.sheets.build_service", return_value=svc):
            result = run(["sheets", "get", "SHEET1", "Sheet1!A1:B2"], capsys)
        assert result == [["Name", "Score"], ["Alice", "95"]]

    def test_update(self, capsys):
        svc = mock_service({"spreadsheets.values.update": {"updatedCells": 2}})
        with patch("suitewright.sheets.build_service", return_value=svc):
            result = run(
                ["sheets", "update", "SHEET1", "A1:B1", "--values", '[["Name","Score"]]'], capsys
            )
        assert isinstance(result, dict)

    def test_append(self, capsys):
        svc = mock_service({"spreadsheets.values.append": {"updates": {"updatedCells": 3}}})
        with patch("suitewright.sheets.build_service", return_value=svc):
            result = run(
                ["sheets", "append", "SHEET1", "A:C", "--values", '[["a","b","c"]]'], capsys
            )
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------


class TestDocsIntegration:
    def _svc(self, doc):
        svc = MagicMock()
        svc.documents().get().execute.return_value = doc
        return svc

    def test_get(self, capsys, sample_doc):
        svc = self._svc(sample_doc)
        with patch("suitewright.docs.basic.build_service", return_value=svc):
            result = run(["docs", "get", "DOC123"], capsys)
        assert result["documentId"] == "DOC123"

    def test_show_structure(self, capsys, sample_doc):
        svc = self._svc(sample_doc)
        with patch("suitewright.docs.basic.build_service", return_value=svc):
            result = run(["docs", "show-structure", "DOC123"], capsys)
        assert "blocks" in result
        assert result["documentId"] == "DOC123"

    def test_show_structure_full_text(self, capsys, sample_doc):
        svc = self._svc(sample_doc)
        with patch("suitewright.docs.basic.build_service", return_value=svc):
            result = run(["docs", "show-structure", "DOC123", "--full-text"], capsys)
        assert "blocks" in result

    def test_create(self, capsys):
        created = {
            "documentId": "NEWDOC",
            "title": "My Doc",
            "webViewLink": "https://docs.google.com/NEWDOC",
        }
        svc = MagicMock()
        svc.documents().create().execute.return_value = created
        with patch("suitewright.docs.basic.build_service", return_value=svc):
            result = run(["docs", "create", "--title", "My Doc"], capsys)
        assert result.get("status") == "created"
        assert result["documentId"] == "NEWDOC"

    def test_request_template_replace_all(self, capsys):
        main(["docs", "request-template", "replace-all"])
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, list)
        assert any("replaceAllText" in r for r in out)

    def test_request_template_insert_table(self, capsys):
        main(["docs", "request-template", "insert-table"])
        out = json.loads(capsys.readouterr().out)
        assert any("insertTable" in r for r in out)

    def test_request_template_insert_image(self, capsys):
        main(["docs", "request-template", "insert-image"])
        out = json.loads(capsys.readouterr().out)
        assert any("insertInlineImage" in r for r in out)

    def test_request_template_style_range(self, capsys):
        main(["docs", "request-template", "style-range"])
        out = json.loads(capsys.readouterr().out)
        assert any("updateTextStyle" in r for r in out)

    def test_update_dry_run(self, capsys):
        requests = [{"insertText": {"location": {"index": 1}, "text": "Hello"}}]
        main(["docs", "update", "DOC123", "--dry-run", "--requests", json.dumps(requests)])
        result = json.loads(capsys.readouterr().out)
        assert result["dryRun"] is True
        assert result["requestCount"] == 1

    def test_table_get(self, capsys, sample_doc):
        svc = self._svc(sample_doc)
        with patch("suitewright.docs.tables.build_service", return_value=svc):
            result = run(["docs", "table-get", "DOC123"], capsys)
        assert "tables" in result
        assert result["tables"][0]["rows"] == 2
        assert result["tables"][0]["cols"] == 3

    def test_table_get_single(self, capsys, sample_doc):
        svc = self._svc(sample_doc)
        with patch("suitewright.docs.tables.build_service", return_value=svc):
            result = run(["docs", "table-get", "DOC123", "--table", "0"], capsys)
        assert "table" in result
        assert result["table"]["tableIndex"] == 0

    def test_comments_list(self, capsys):
        svc = MagicMock()
        svc.comments().list().execute.return_value = {
            "comments": [
                {
                    "id": "c1",
                    "content": "Nice work",
                    "author": {"displayName": "Bob"},
                    "createdTime": "2025-01-15T00:00:00Z",
                    "modifiedTime": "2025-01-15T00:00:00Z",
                    "resolved": False,
                    "deleted": False,
                }
            ]
        }
        with patch("suitewright.docs.comments.build_service", return_value=svc):
            result = run(["docs", "comments", "list", "DOC123"], capsys)
        assert "comments" in result

    def test_plan(self, capsys, sample_doc, tmp_requests_file):
        requests = [{"insertText": {"location": {"index": 1}, "text": "Hello"}}]
        req_file = tmp_requests_file(requests)
        svc = self._svc(sample_doc)
        with patch("suitewright.docs.plan.build_service", return_value=svc):
            main(["docs", "plan", "DOC123", "--requests-file", req_file])
        result = json.loads(capsys.readouterr().out)
        assert result["documentId"] == "DOC123"
        assert result["summary"]["requestCount"] == 1


# ---------------------------------------------------------------------------
# Forms - direct API commands
# ---------------------------------------------------------------------------


class TestFormsApiIntegration:
    def test_list(self, capsys):
        files = [
            {
                "id": "f1",
                "name": "My Form",
                "mimeType": "application/vnd.google-apps.form",
                "modifiedTime": "2025-01-15",
                "webViewLink": "https://forms.google.com/f1",
            }
        ]
        svc = mock_service({"files.list": {"files": files}})
        with patch("suitewright.forms.api.build_service", return_value=svc):
            result = run(["forms", "list"], capsys)
        assert isinstance(result, list)
        assert result[0]["id"] == "f1"

    def test_get(self, capsys, sample_form):
        svc = mock_service({"forms.get": sample_form})
        with patch("suitewright.forms.api.build_service", return_value=svc):
            result = run(["forms", "get", "FORM123"], capsys)
        assert result["formId"] == "FORM123"

    def test_create(self, capsys):
        created = {"formId": "NEWFORM", "info": {"title": "Survey"}}
        svc = mock_service({"forms.create": created})
        with patch("suitewright.forms.api.build_service", return_value=svc):
            result = run(["forms", "create", "--title", "Survey"], capsys)
        assert result["formId"] == "NEWFORM"

    def test_update(self, capsys):
        resp = {"replies": []}
        svc = mock_service({"forms.batchUpdate": resp})
        requests = [{"updateFormInfo": {"info": {"title": "New Title"}, "updateMask": "title"}}]
        with patch("suitewright.forms.api.build_service", return_value=svc):
            result = run(["forms", "update", "FORM123", "--requests", json.dumps(requests)], capsys)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Forms - state lifecycle (fetch / show-cache / validate / cache-update)
# ---------------------------------------------------------------------------


class TestFormsStateIntegration:
    def test_fetch(self, capsys, sample_form, tmp_path):
        svc = mock_service({"forms.get": sample_form})
        with patch("suitewright.forms.state.build_service", return_value=svc):
            with patch(
                "suitewright.forms.state.cache_path", return_value=tmp_path / "FORM123.json"
            ):
                with patch("suitewright.forms.cache.cache_root", return_value=tmp_path):
                    main(["forms", "fetch", "FORM123"])
        out = capsys.readouterr().out.strip()
        assert out != ""

    def test_show_cache(self, capsys, sample_form, tmp_path):
        cache_file = tmp_path / "FORM123.json"
        cache_file.write_text(json.dumps(sample_form))
        with patch("suitewright.forms.state.cache_path", return_value=cache_file):
            main(["forms", "show-cache", "FORM123"])
        out = capsys.readouterr().out.strip()
        assert "FORM123" in out

    def test_validate_ok(self, capsys, sample_form, tmp_path):
        cache_file = tmp_path / "FORM123.json"
        cache_file.write_text(json.dumps(sample_form))
        with patch("suitewright.forms.state.cache_path", return_value=cache_file):
            main(["forms", "validate", "FORM123"])
        out = capsys.readouterr().out.strip()
        assert out != ""

    def test_validate_stale_revision(self, capsys, sample_form, tmp_path):
        cache_file = tmp_path / "FORM123.json"
        cache_file.write_text(json.dumps(sample_form))
        with patch("suitewright.forms.state.cache_path", return_value=cache_file):
            with pytest.raises(SystemExit):
                main(["forms", "validate", "FORM123", "--expected-revision", "wrong_rev"])

    def test_validate_expect_item_id_found(self, capsys, sample_form, tmp_path):
        cache_file = tmp_path / "FORM123.json"
        cache_file.write_text(json.dumps(sample_form))
        with patch("suitewright.forms.state.cache_path", return_value=cache_file):
            main(["forms", "validate", "FORM123", "--expect-item-id", "item001"])
        out = capsys.readouterr().out.strip()
        assert out != ""

    def test_validate_expect_item_id_missing(self, capsys, sample_form, tmp_path):
        cache_file = tmp_path / "FORM123.json"
        cache_file.write_text(json.dumps(sample_form))
        with patch("suitewright.forms.state.cache_path", return_value=cache_file):
            with pytest.raises(SystemExit):
                main(["forms", "validate", "FORM123", "--expect-item-id", "nonexistent"])


# ---------------------------------------------------------------------------
# Forms - query helpers (cache-first)
# ---------------------------------------------------------------------------


class TestFormsQueryIntegration:
    def _write_cache(self, tmp_path, form):
        f = tmp_path / f"{form['formId']}.json"
        f.write_text(json.dumps(form))
        return f

    def test_locate_by_item_id(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(["forms", "query", "locate", "FORM123", "--item-id", "item001"], capsys)
        assert result["index"] == 0

    def test_locate_by_title(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(
                ["forms", "query", "locate", "FORM123", "--title", "A1. First question"], capsys
            )
        assert result["index"] == 0

    def test_after(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(["forms", "query", "after", "FORM123", "--item-id", "item001"], capsys)
        assert result["afterIndex"] == 1

    def test_delete_request(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(
                ["forms", "query", "delete-request", "FORM123", "--item-id", "item001"], capsys
            )
        assert isinstance(result, list)
        assert result[0]["deleteItem"]["location"]["index"] == 0

    def test_get_item(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(["forms", "query", "get-item", "FORM123", "--item-id", "item001"], capsys)
        assert result["itemId"] == "item001"
        assert result["kind"] == "questionItem"

    def test_neighbors(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(
                [
                    "forms",
                    "query",
                    "neighbors",
                    "FORM123",
                    "--item-id",
                    "item002",
                    "--before",
                    "1",
                    "--after",
                    "1",
                ],
                capsys,
            )
        assert isinstance(result, list)
        assert len(result) == 3

    def test_section(self, capsys, tmp_path):
        form = {
            "formId": "FORM999",
            "revisionId": "r1",
            "items": [
                {"itemId": "s1", "title": "Bagian 1", "textItem": {}},
                {
                    "itemId": "q1",
                    "title": "Q1",
                    "questionItem": {"question": {"questionId": "qq1", "textQuestion": {}}},
                },
                {"itemId": "s2", "title": "Bagian 2", "textItem": {}},
            ],
        }
        cache_file = self._write_cache(tmp_path, form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(["forms", "query", "section", "FORM999", "--item-id", "q1"], capsys)
        assert isinstance(result, list)
        titles = [i["title"] for i in result]
        assert "Bagian 1" in titles
        assert "Q1" in titles
        assert "Bagian 2" not in titles

    def test_indexer(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(["forms", "query", "indexer", "FORM123"], capsys)
        assert result["matchCount"] == 2
        labels = [m["label"] for m in result["matches"]]
        assert "A1." in labels
        assert "B2." in labels

    def test_indexer_no_match(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            result = run(["forms", "query", "indexer", "FORM123", "--pattern", r"^NOMATCH"], capsys)
        assert result["matchCount"] == 0

    def test_locate_not_found(self, capsys, sample_form, tmp_path):
        cache_file = self._write_cache(tmp_path, sample_form)
        with patch("suitewright.forms.query.cache_path", return_value=cache_file):
            with pytest.raises(SystemExit):
                main(["forms", "query", "locate", "FORM123", "--item-id", "nonexistent"])
