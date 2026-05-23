"""Docs mutate subcommand group: semantic write helpers with cache guards.

All write operations validate cache freshness before executing, include
writeControl.requiredRevisionId when available, and auto-refresh the local
cache after success. Every command supports --dry-run.

Shared helpers `load_docs_requests` and `summarize_docs_requests` are
canonical here (moved from basic.py); also used by plan.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from suitewright._core.cache import CacheStore
from suitewright._core.output import emit_json, error_exit, warn
from suitewright._core.render import document_end_index
from suitewright._core.retry import execute_with_backoff
from suitewright._core.service import build_service
from suitewright.docs.state import _build_batch_update_body, fetch_doc

_cache = CacheStore("docs")


# ---------------------------------------------------------------------------
# Shared request-loading helpers (moved from basic.py)
# ---------------------------------------------------------------------------


def load_docs_requests(args) -> list[dict]:
    """Load batchUpdate requests from --requests (inline JSON) or --requests-file.

    Exactly one of the two must be provided. Returns a validated list of dicts.
    """
    if bool(args.requests) == bool(args.requests_file):
        raise SystemExit("Provide exactly one of --requests or --requests-file")

    if args.requests:
        try:
            payload = json.loads(args.requests)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON in --requests: {exc}") from exc
    else:
        request_path = Path(args.requests_file)
        if not request_path.exists():
            raise SystemExit(f"Requests file not found: {request_path}")
        try:
            payload = json.loads(request_path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON in --requests-file: {exc}") from exc

    if not isinstance(payload, list):
        raise SystemExit("Docs update payload must be a JSON list of requests")
    return payload


def summarize_docs_requests(requests: list[dict]) -> list[dict]:
    """Produce a summary list with index and kind for each request."""
    summary = []
    for index, request in enumerate(requests):
        if isinstance(request, dict) and request:
            kind = next(iter(request.keys()))
        else:
            kind = "unknown"
        summary.append({"index": index, "kind": kind})
    return summary


# ---------------------------------------------------------------------------
# Guarded mutate core
# ---------------------------------------------------------------------------


def guarded_mutate(doc_id: str, requests: list[dict], *, dry_run: bool = False) -> dict:
    """Validate cache → execute batchUpdate → refresh cache → return result.

    Steps:
    1. Validate cache exists
    2. Check revisionId staleness (compare cached vs live if available, else warn)
    3. If dry_run, return without executing
    4. Execute batchUpdate with writeControl.requiredRevisionId when available
    5. Re-fetch and overwrite cache
    """
    # 1. Validate cache exists
    if not _cache.exists(doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=doc_id,
            expectedPath=str(_cache.path(doc_id)),
        )

    cached = _cache.load(doc_id)
    revision_id = cached.get("revisionId")

    # 2. Check revisionId staleness
    if revision_id:
        service = build_service("docs", "v1")
        live_doc = execute_with_backoff(
            lambda: service.documents().get(documentId=doc_id, fields="revisionId").execute()
        )
        live_revision = live_doc.get("revisionId")
        if revision_id != live_revision:
            error_exit(
                "stale",
                "REVISION_MISMATCH",
                "Document changed since last fetch. Run `docs cache fetch` first.",
                cachedRevision=revision_id,
                liveRevision=live_revision,
            )
    else:
        warn(
            "No revisionId in cache. Cannot verify remote staleness. "
            "Proceeding with cacheHash-only validation.",
            documentId=doc_id,
        )

    # 3. Dry-run check
    if dry_run:
        return {"status": "dry-run", "requestCount": len(requests), "requests": requests}

    # 4. Execute batchUpdate with writeControl when possible
    body = _build_batch_update_body(requests, revision_id)
    service = build_service("docs", "v1")
    result = execute_with_backoff(
        lambda: service.documents().batchUpdate(documentId=doc_id, body=body).execute()
    )

    # 5. Refresh cache
    fresh = fetch_doc(doc_id)
    cache_path = _cache.write(doc_id, fresh)

    return {
        "status": "updated",
        "documentId": doc_id,
        "cachePath": str(cache_path),
        "revisionId": fresh.get("revisionId"),
        "batchUpdateResponse": result,
    }


# ---------------------------------------------------------------------------
# Table helpers (cell resolution + rectangular validation)
# Preserved from tables.py, adapted to use guarded_mutate wrapper.
# ---------------------------------------------------------------------------


def _collect_tables(doc: dict) -> list[tuple[int, dict]]:
    """Collect all top-level tables from the document body."""
    out = []
    for block_idx, element in enumerate(doc.get("body", {}).get("content", [])):
        if "table" in element:
            out.append((block_idx, element))
    return out


def _ensure_rectangular(table: dict) -> None:
    """Reject tables whose cells contain non-paragraph content."""
    for r_idx, row in enumerate(table.get("tableRows", [])):
        for c_idx, cell in enumerate(row.get("tableCells", [])):
            for elem in cell.get("content", []):
                if "paragraph" not in elem:
                    raise SystemExit(
                        f"Table cell at row={r_idx} col={c_idx} contains "
                        "non-paragraph content (nested table, image, list, etc.); "
                        "suitewright table helpers only support rectangular text-only tables."
                    )


def _resolve_cell(table: dict, row: int, col: int) -> dict:
    """Resolve a specific cell by row/col index."""
    rows = table.get("tableRows", [])
    if row >= len(rows):
        raise SystemExit(f"--row {row} out of range (table has {len(rows)} rows)")
    cells = rows[row].get("tableCells", [])
    if col >= len(cells):
        raise SystemExit(f"--col {col} out of range (row has {len(cells)} cells)")
    return cells[col]


def _cell_inner_range(cell: dict) -> tuple[int, int]:
    """Compute the deletable range covering existing cell text content.

    The cell's structural range includes a trailing newline that belongs to
    the cell itself; deleting up to but not including that newline keeps the
    cell intact while clearing its text.
    """
    paragraphs = [e for e in cell.get("content", []) if "paragraph" in e]
    if not paragraphs:
        start = cell.get("startIndex", 0)
        return start, start
    start = paragraphs[0].get("startIndex", 0)
    end = paragraphs[-1].get("endIndex", start)
    return start, max(start, end - 1)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_append(args) -> None:
    """Append text at end of document using guarded_mutate."""
    if not args.text:
        raise SystemExit("--text must be a non-empty string")

    cached = _cache.load(args.doc_id)
    end_index = max(1, document_end_index(cached) - 1)

    requests = [{"insertText": {"location": {"index": end_index}, "text": args.text}}]

    dry_run = getattr(args, "dry_run", False)
    result = guarded_mutate(args.doc_id, requests, dry_run=dry_run)

    compact = getattr(args, "compact", False)
    if dry_run:
        emit_json(result, compact=compact)
    else:
        emit_json(
            {
                "status": "appended",
                "documentId": args.doc_id,
                "inserted_at": end_index,
                "characters": len(args.text),
            },
            compact=compact,
        )


def cmd_replace(args) -> None:
    """Replace full document body with new text using guarded_mutate."""
    cached = _cache.load(args.doc_id)
    end_index = max(1, document_end_index(cached) - 1)

    requests: list[dict] = []
    if end_index > 1:
        requests.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index}}})
    if args.text:
        requests.append({"insertText": {"location": {"index": 1}, "text": args.text}})

    dry_run = getattr(args, "dry_run", False)
    result = guarded_mutate(args.doc_id, requests, dry_run=dry_run)

    compact = getattr(args, "compact", False)
    if dry_run:
        emit_json(result, compact=compact)
    else:
        emit_json(
            {
                "status": "replaced",
                "documentId": args.doc_id,
                "characters": len(args.text),
            },
            compact=compact,
        )


def cmd_replace_all(args) -> None:
    """Find and replace all occurrences using guarded_mutate."""
    if not args.find:
        raise SystemExit("--find must be a non-empty string")

    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": args.find, "matchCase": True},
                "replaceText": args.replace,
            }
        }
    ]

    dry_run = getattr(args, "dry_run", False)
    result = guarded_mutate(args.doc_id, requests, dry_run=dry_run)

    compact = getattr(args, "compact", False)
    if dry_run:
        emit_json(result, compact=compact)
    else:
        # Extract occurrences from batchUpdate response
        occurrences = 0
        replies = result.get("batchUpdateResponse", {}).get("replies") or []
        if replies:
            occurrences = replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
        emit_json(
            {
                "status": "replaced",
                "documentId": args.doc_id,
                "find": args.find,
                "replace": args.replace,
                "matchCase": True,
                "occurrencesChanged": occurrences,
            },
            compact=compact,
        )


def cmd_insert_table(args) -> None:
    """Insert a table at the specified index using guarded_mutate."""
    if args.rows <= 0:
        raise SystemExit("--rows must be > 0")
    if args.cols <= 0:
        raise SystemExit("--cols must be > 0")
    if args.index < 1:
        raise SystemExit("--index must be >= 1")

    requests = [
        {
            "insertTable": {
                "rows": args.rows,
                "columns": args.cols,
                "location": {"index": args.index},
            }
        }
    ]

    dry_run = getattr(args, "dry_run", False)
    result = guarded_mutate(args.doc_id, requests, dry_run=dry_run)

    compact = getattr(args, "compact", False)
    if dry_run:
        emit_json(result, compact=compact)
    else:
        emit_json(
            {
                "status": "inserted",
                "documentId": args.doc_id,
                "rows": args.rows,
                "cols": args.cols,
                "index": args.index,
                "requestKind": "insertTable",
            },
            compact=compact,
        )


def cmd_insert_image(args) -> None:
    """Insert an inline image at the specified index using guarded_mutate."""
    if not args.uri:
        raise SystemExit("--uri must be a non-empty URL")
    if args.index < 1:
        raise SystemExit("--index must be >= 1")

    requests = [
        {
            "insertInlineImage": {
                "uri": args.uri,
                "location": {"index": args.index},
            }
        }
    ]

    dry_run = getattr(args, "dry_run", False)
    result = guarded_mutate(args.doc_id, requests, dry_run=dry_run)

    compact = getattr(args, "compact", False)
    if dry_run:
        emit_json(result, compact=compact)
    else:
        emit_json(
            {
                "status": "inserted",
                "documentId": args.doc_id,
                "uri": args.uri,
                "index": args.index,
                "requestKind": "insertInlineImage",
            },
            compact=compact,
        )


def cmd_style_range(args) -> None:
    """Apply text style to a range using guarded_mutate."""
    if args.start_index < 1:
        raise SystemExit("--start-index must be >= 1")
    if args.end_index <= args.start_index:
        raise SystemExit("--end-index must be > --start-index")

    text_style: dict = {}
    fields_set: list[str] = []
    if args.bold:
        text_style["bold"] = True
        fields_set.append("bold")

    if not text_style:
        raise SystemExit("Provide at least one style flag (currently supported: --bold)")

    fields_mask = ",".join(fields_set)
    requests = [
        {
            "updateTextStyle": {
                "range": {"startIndex": args.start_index, "endIndex": args.end_index},
                "textStyle": text_style,
                "fields": fields_mask,
            }
        }
    ]

    dry_run = getattr(args, "dry_run", False)
    result = guarded_mutate(args.doc_id, requests, dry_run=dry_run)

    compact = getattr(args, "compact", False)
    if dry_run:
        emit_json(result, compact=compact)
    else:
        emit_json(
            {
                "status": "styled",
                "documentId": args.doc_id,
                "startIndex": args.start_index,
                "endIndex": args.end_index,
                "fields": fields_mask,
                "requestKind": "updateTextStyle",
            },
            compact=compact,
        )


def cmd_table_update_cell(args) -> None:
    """Update one table cell's text using guarded_mutate.

    Preserves existing cell-resolution and rectangular-validation logic
    from tables.py, adds cache staleness check + auto-refresh.
    """
    if args.table < 0:
        raise SystemExit("--table must be >= 0")
    if args.row < 0:
        raise SystemExit("--row must be >= 0")
    if args.col < 0:
        raise SystemExit("--col must be >= 0")
    if not args.text:
        raise SystemExit("--text must be a non-empty string")

    cached = _cache.load(args.doc_id)
    tables = _collect_tables(cached)
    if args.table >= len(tables):
        raise SystemExit(f"--table {args.table} out of range (document has {len(tables)} tables)")

    _, element = tables[args.table]
    table = element["table"]
    _ensure_rectangular(table)
    cell = _resolve_cell(table, args.row, args.col)
    start, end = _cell_inner_range(cell)

    requests: list[dict] = []
    if end > start:
        requests.append({"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}})
    requests.append({"insertText": {"location": {"index": start}, "text": args.text}})

    dry_run = getattr(args, "dry_run", False)
    result = guarded_mutate(args.doc_id, requests, dry_run=dry_run)

    compact = getattr(args, "compact", False)
    if dry_run:
        emit_json(result, compact=compact)
    else:
        emit_json(
            {
                "status": "updated",
                "documentId": args.doc_id,
                "tableIndex": args.table,
                "row": args.row,
                "col": args.col,
                "text": args.text,
            },
            compact=compact,
        )


def cmd_table_append_row(args) -> None:
    """Append a row to a table using guarded_mutate.

    Preserves existing cell-resolution and rectangular-validation logic
    from tables.py, adds cache staleness check + auto-refresh.

    Two-phase approach:
    1. Insert the row via guarded_mutate (validates staleness + refreshes cache)
    2. Fill cell text via a second guarded_mutate on the refreshed cache
    """
    if args.table < 0:
        raise SystemExit("--table must be >= 0")

    try:
        values = json.loads(args.values)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--values is not valid JSON: {exc}") from exc
    if not isinstance(values, list):
        raise SystemExit("--values must be a JSON array of cell strings")
    if not all(isinstance(v, str) for v in values):
        raise SystemExit("--values entries must all be strings")

    cached = _cache.load(args.doc_id)
    tables = _collect_tables(cached)
    if args.table >= len(tables):
        raise SystemExit(f"--table {args.table} out of range (document has {len(tables)} tables)")

    _, element = tables[args.table]
    table = element["table"]
    _ensure_rectangular(table)
    rows = table.get("tableRows", [])
    if not rows:
        raise SystemExit(f"Table {args.table} has no existing rows to append after")

    cols = max(len(row.get("tableCells", [])) for row in rows)
    if len(values) != cols:
        raise SystemExit(f"--values length {len(values)} must match table column count {cols}")

    dry_run = getattr(args, "dry_run", False)

    # Phase 1: Insert the row
    insert_request = {
        "insertTableRow": {
            "tableCellLocation": {
                "tableStartLocation": {"index": element.get("startIndex", 1)},
                "rowIndex": len(rows) - 1,
                "columnIndex": 0,
            },
            "insertBelow": True,
        }
    }

    if dry_run:
        # For dry-run, show the full plan (insert + text fills)
        text_requests_preview = [
            {"insertText": {"location": {"index": "TBD"}, "text": value}} for value in values
        ]
        all_requests = [insert_request, *text_requests_preview]
        result = {"status": "dry-run", "requestCount": len(all_requests), "requests": all_requests}
        compact = getattr(args, "compact", False)
        emit_json(result, compact=compact)
        return

    # Execute row insertion with guarded_mutate (validates + refreshes cache)
    guarded_mutate(args.doc_id, [insert_request], dry_run=False)

    # Phase 2: Fill cell text using refreshed cache
    refreshed = _cache.load(args.doc_id)
    new_tables = _collect_tables(refreshed)
    new_table = new_tables[args.table][1]["table"]
    new_rows = new_table.get("tableRows", [])
    new_row = new_rows[len(rows)]  # The newly inserted row

    text_requests: list[dict] = []
    for col_idx, value in enumerate(values):
        cell = new_row.get("tableCells", [])[col_idx]
        start, _ = _cell_inner_range(cell)
        text_requests.append({"insertText": {"location": {"index": start}, "text": value}})

    if text_requests:
        # Apply right-to-left to keep earlier indexes stable
        text_requests.reverse()
        guarded_mutate(args.doc_id, text_requests, dry_run=False)

    compact = getattr(args, "compact", False)
    emit_json(
        {
            "status": "appended",
            "documentId": args.doc_id,
            "tableIndex": args.table,
            "values": values,
            "columnCount": cols,
        },
        compact=compact,
    )


def cmd_raw(args) -> None:
    """Send raw batchUpdate request payload using guarded_mutate.

    Supports both --requests (inline JSON) and --requests-file.
    """
    requests = load_docs_requests(args)

    dry_run = getattr(args, "dry_run", False)
    result = guarded_mutate(args.doc_id, requests, dry_run=dry_run)

    compact = getattr(args, "compact", False)
    if dry_run:
        emit_json(result, compact=compact)
    else:
        emit_json(result, compact=compact)


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


def register(sub: argparse._SubParsersAction) -> None:
    """Register all mutate subcommands under the mutate group."""
    # append
    p = sub.add_parser("append", help="Append text at end of document")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--text", required=True, help="Text to append")
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_append)

    # replace
    p = sub.add_parser("replace", help="Replace full document body with new text")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--text", required=True, help="Replacement text")
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_replace)

    # replace-all
    p = sub.add_parser("replace-all", help="Find and replace all occurrences")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--find", required=True, help="String to find (matchCase=true)")
    p.add_argument("--replace", required=True, help="Replacement string (may be empty)")
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_replace_all)

    # insert-table
    p = sub.add_parser("insert-table", help="Insert a table at a structural index")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--rows", type=int, required=True)
    p.add_argument("--cols", type=int, required=True)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_insert_table)

    # insert-image
    p = sub.add_parser("insert-image", help="Insert an inline image at a structural index")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--uri", required=True, help="Public URL to image")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_insert_image)

    # style-range
    p = sub.add_parser("style-range", help="Apply text style to a range")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--start-index", type=int, required=True)
    p.add_argument("--end-index", type=int, required=True)
    p.add_argument("--bold", action="store_true", help="Set bold=true on the range")
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_style_range)

    # table-update-cell
    p = sub.add_parser("table-update-cell", help="Update one table cell's text")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--table", type=int, required=True, help="Zero-based table index")
    p.add_argument("--row", type=int, required=True)
    p.add_argument("--col", type=int, required=True)
    p.add_argument("--text", required=True, help="New cell text")
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_table_update_cell)

    # table-append-row
    p = sub.add_parser("table-append-row", help="Append one row of cell values to a table")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--table", type=int, required=True, help="Zero-based table index")
    p.add_argument("--values", required=True, help="JSON array of cell strings")
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_table_append_row)

    # raw
    p = sub.add_parser("raw", help="Send raw batchUpdate request payload")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--requests", default="", help="JSON list of batchUpdate requests (inline)")
    p.add_argument(
        "--requests-file", default="", help="Path to JSON file with batchUpdate requests"
    )
    p.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_raw)
