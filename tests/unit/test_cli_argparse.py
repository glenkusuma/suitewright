"""Tests for the CLI argparse surface.

These tests verify --help, --version, missing required args, invalid types,
and mutually exclusive groups - all without hitting the Google API.
"""

from __future__ import annotations

import pytest

from suitewright.cli import build_parser


def parse(args: list[str]):
    """Parse args, returning the namespace. Raises SystemExit on error."""
    return build_parser().parse_args(args)


def assert_help(args: list[str], expected_text: str):
    with pytest.raises(SystemExit) as exc:
        parse(args)
    assert exc.value.code == 0


def assert_error(args: list[str]):
    with pytest.raises(SystemExit) as exc:
        parse(args)
    assert exc.value.code != 0


class TestVersion:
    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            parse(["--version"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "0.0.1" in captured.out


class TestTopLevel:
    def test_help(self, capsys):
        assert_help(["--help"], "suitewright")

    def test_no_args_exits(self):
        assert_error([])


class TestAuthArgparse:
    def test_help(self, capsys):
        assert_help(["auth", "--help"], "auth")

    def test_init_requires_client_secret(self):
        assert_error(["auth", "init"])

    def test_init_with_client_secret(self):
        ns = parse(["auth", "init", "--client-secret", "/tmp/secret.json"])
        assert ns.client_secret == "/tmp/secret.json"

    def test_login_no_flags(self):
        ns = parse(["auth", "login"])
        assert not ns.auth_url
        assert ns.auth_code == ""

    def test_login_auth_url_flag(self):
        ns = parse(["auth", "login", "--auth-url"])
        assert ns.auth_url is True

    def test_login_auth_code_flag(self):
        ns = parse(["auth", "login", "--auth-code", "mycode"])
        assert ns.auth_code == "mycode"

    def test_check_parses(self):
        ns = parse(["auth", "check"])
        assert hasattr(ns, "func")

    def test_revoke_parses(self):
        ns = parse(["auth", "revoke"])
        assert hasattr(ns, "func")


class TestGmailArgparse:
    def test_help(self, capsys):
        assert_help(["gmail", "--help"], "gmail")

    def test_search_requires_query(self):
        assert_error(["gmail", "search"])

    def test_search_with_query(self):
        ns = parse(["gmail", "search", "is:unread"])
        assert ns.query == "is:unread"

    def test_search_default_max(self):
        ns = parse(["gmail", "search", "test"])
        assert ns.max == 10

    def test_send_requires_to_subject_body(self):
        assert_error(["gmail", "send", "--to", "a@b.com"])
        assert_error(["gmail", "send", "--subject", "Hi"])
        assert_error(["gmail", "send", "--body", "Hello"])

    def test_send_all_required(self):
        ns = parse(["gmail", "send", "--to", "a@b.com", "--subject", "Hi", "--body", "Hello"])
        assert ns.to == "a@b.com"


class TestCalendarArgparse:
    def test_help(self, capsys):
        assert_help(["calendar", "--help"], "calendar")

    def test_list_requires_calendar(self):
        assert_error(["calendar", "list"])

    def test_list_with_calendar(self):
        ns = parse(["calendar", "list", "--calendar", "primary"])
        assert ns.calendar == "primary"

    def test_create_requires_summary_start_end_calendar(self):
        assert_error(["calendar", "create", "--summary", "Meeting"])

    def test_create_all_required(self):
        ns = parse(
            [
                "calendar",
                "create",
                "--summary",
                "Meeting",
                "--start",
                "2025-01-15T10:00:00+07:00",
                "--end",
                "2025-01-15T11:00:00+07:00",
                "--calendar",
                "primary",
            ]
        )
        assert ns.summary == "Meeting"


class TestDriveArgparse:
    def test_help(self, capsys):
        assert_help(["drive", "--help"], "drive")

    def test_get_requires_file_id(self):
        assert_error(["drive", "get"])

    def test_get_with_file_id(self):
        ns = parse(["drive", "get", "FILE123"])
        assert ns.file_id == "FILE123"

    def test_upload_requires_path(self):
        assert_error(["drive", "upload"])

    def test_upload_with_path(self):
        ns = parse(["drive", "upload", "/tmp/file.txt"])
        assert ns.path == "/tmp/file.txt"

    def test_share_requires_email_and_role(self):
        assert_error(["drive", "share", "FILE123", "--email", "a@b.com"])
        assert_error(["drive", "share", "FILE123", "--role", "reader"])

    def test_share_invalid_role(self):
        assert_error(["drive", "share", "FILE123", "--email", "a@b.com", "--role", "owner"])

    def test_share_valid_role(self):
        ns = parse(["drive", "share", "FILE123", "--email", "a@b.com", "--role", "reader"])
        assert ns.role == "reader"

    def test_delete_default_no_permanent(self):
        ns = parse(["drive", "delete", "FILE123"])
        assert ns.permanent is False

    def test_delete_permanent_flag(self):
        ns = parse(["drive", "delete", "FILE123", "--permanent"])
        assert ns.permanent is True


class TestDocsArgparse:
    def test_help(self, capsys):
        assert_help(["docs", "--help"], "docs")

    def test_cache_help(self, capsys):
        assert_help(["docs", "cache", "--help"], "cache")

    def test_query_help(self, capsys):
        assert_help(["docs", "query", "--help"], "query")

    def test_mutate_help(self, capsys):
        assert_help(["docs", "mutate", "--help"], "mutate")

    def test_table_help(self, capsys):
        assert_help(["docs", "table", "--help"], "table")

    def test_cache_fetch_requires_doc_id(self):
        assert_error(["docs", "cache", "fetch"])

    def test_cache_fetch_with_doc_id(self):
        ns = parse(["docs", "cache", "fetch", "DOC123"])
        assert ns.doc_id == "DOC123"

    def test_query_structure_requires_doc_id(self):
        assert_error(["docs", "query", "structure"])

    def test_query_structure_full_text_flag(self):
        ns = parse(["docs", "query", "structure", "DOC123", "--full-text"])
        assert ns.full_text is True

    def test_create_requires_title(self):
        assert_error(["docs", "create"])

    def test_create_with_title(self):
        ns = parse(["docs", "create", "--title", "My Doc"])
        assert ns.title == "My Doc"

    def test_mutate_insert_table_requires_all(self):
        assert_error(["docs", "mutate", "insert-table", "DOC123", "--rows", "2"])

    def test_mutate_insert_table_all_args(self):
        ns = parse(
            [
                "docs",
                "mutate",
                "insert-table",
                "DOC123",
                "--rows",
                "2",
                "--cols",
                "3",
                "--index",
                "1",
            ]
        )
        assert ns.rows == 2
        assert ns.cols == 3
        assert ns.index == 1

    def test_mutate_insert_table_invalid_type(self):
        assert_error(
            [
                "docs",
                "mutate",
                "insert-table",
                "DOC123",
                "--rows",
                "abc",
                "--cols",
                "3",
                "--index",
                "1",
            ]
        )

    def test_table_get_optional_table(self):
        ns = parse(["docs", "table", "get", "DOC123"])
        assert ns.table is None

    def test_table_get_with_table(self):
        ns = parse(["docs", "table", "get", "DOC123", "--table", "0"])
        assert ns.table == 0

    def test_mutate_style_range_requires_indexes(self):
        assert_error(["docs", "mutate", "style-range", "DOC123"])

    def test_mutate_style_range_with_bold(self):
        ns = parse(
            [
                "docs",
                "mutate",
                "style-range",
                "DOC123",
                "--start-index",
                "1",
                "--end-index",
                "10",
                "--bold",
            ]
        )
        assert ns.bold is True

    def test_request_template_kinds(self):
        for kind in ["replace-all", "insert-table", "insert-image", "style-range"]:
            ns = parse(["docs", "request-template", kind])
            assert hasattr(ns, "func")

    def test_comments_subcommands(self):
        ns = parse(["docs", "comments", "list", "DOC123"])
        assert ns.doc_id == "DOC123"

    def test_plan_requires_requests_file(self):
        assert_error(["docs", "plan", "DOC123"])

    def test_plan_with_requests_file(self):
        ns = parse(["docs", "plan", "DOC123", "--requests-file", "/tmp/req.json"])
        assert ns.requests_file == "/tmp/req.json"

    # Verify old flat commands no longer exist
    def test_old_flat_get_removed(self):
        assert_error(["docs", "get"])

    def test_old_flat_show_structure_removed(self):
        assert_error(["docs", "show-structure"])

    def test_old_flat_table_get_removed(self):
        assert_error(["docs", "table-get"])


class TestFormsArgparse:
    def test_help(self, capsys):
        assert_help(["forms", "--help"], "forms")

    def test_no_forms_cache_top_level(self):
        assert_error(["forms-cache", "fetch", "FORM123"])

    def test_fetch_requires_form_id(self):
        assert_error(["forms", "fetch"])

    def test_fetch_with_form_id(self):
        ns = parse(["forms", "fetch", "FORM123"])
        assert ns.form_id == "FORM123"

    def test_show_cache_with_form_id(self):
        ns = parse(["forms", "show-cache", "FORM123"])
        assert ns.form_id == "FORM123"

    def test_validate_with_form_id(self):
        ns = parse(["forms", "validate", "FORM123"])
        assert ns.form_id == "FORM123"

    def test_cache_update_requires_requests_file(self):
        assert_error(["forms", "cache-update", "FORM123"])

    def test_cache_update_with_requests_file(self):
        ns = parse(["forms", "cache-update", "FORM123", "/tmp/req.json"])
        assert ns.form_id == "FORM123"
        assert ns.requests_file == "/tmp/req.json"

    def test_query_help(self, capsys):
        assert_help(["forms", "query", "--help"], "query")

    def test_query_locate_requires_item_id_or_title(self):
        assert_error(["forms", "query", "locate", "FORM123"])

    def test_query_locate_with_item_id(self):
        ns = parse(["forms", "query", "locate", "FORM123", "--item-id", "item001"])
        assert ns.item_id == "item001"

    def test_query_locate_with_title(self):
        ns = parse(["forms", "query", "locate", "FORM123", "--title", "My Question"])
        assert ns.title == "My Question"

    def test_query_locate_both_raises(self):
        assert_error(["forms", "query", "locate", "FORM123", "--item-id", "x", "--title", "y"])

    def test_query_indexer_default_pattern(self):
        ns = parse(["forms", "query", "indexer", "FORM123"])
        assert ns.pattern == r"^[A-Z]\d+\."

    def test_query_indexer_custom_pattern(self):
        ns = parse(["forms", "query", "indexer", "FORM123", "--pattern", r"^Q\d+\."])
        assert ns.pattern == r"^Q\d+\."

    def test_query_neighbors_defaults(self):
        ns = parse(["forms", "query", "neighbors", "FORM123", "--item-id", "x"])
        assert ns.before == 1
        assert ns.after == 1

    def test_query_after_with_title(self):
        ns = parse(["forms", "query", "after", "FORM123", "--title", "Q1"])
        assert ns.title == "Q1"

    def test_query_delete_request_with_item_id(self):
        ns = parse(["forms", "query", "delete-request", "FORM123", "--item-id", "item001"])
        assert ns.item_id == "item001"

    def test_query_get_item_with_title(self):
        ns = parse(["forms", "query", "get-item", "FORM123", "--title", "Q1"])
        assert ns.title == "Q1"

    def test_query_section_with_item_id(self):
        ns = parse(["forms", "query", "section", "FORM123", "--item-id", "item001"])
        assert ns.item_id == "item001"


class TestSheetsArgparse:
    def test_get_requires_sheet_id_and_range(self):
        assert_error(["sheets", "get"])
        assert_error(["sheets", "get", "SHEET123"])

    def test_get_with_args(self):
        ns = parse(["sheets", "get", "SHEET123", "A1:B10"])
        assert ns.sheet_id == "SHEET123"
        assert ns.range == "A1:B10"

    def test_update_requires_values(self):
        assert_error(["sheets", "update", "SHEET123", "A1:B2"])

    def test_update_with_values(self):
        ns = parse(["sheets", "update", "SHEET123", "A1:B2", "--values", "[[1,2]]"])
        assert ns.values == "[[1,2]]"


class TestContactsArgparse:
    def test_list_parses(self):
        ns = parse(["contacts", "list"])
        assert hasattr(ns, "func")

    def test_list_default_max(self):
        ns = parse(["contacts", "list"])
        assert ns.max == 50
