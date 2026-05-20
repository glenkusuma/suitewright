"""Docs table-aware helpers: table-get / table-update-cell / table-append-row.

Index model:
- `tableIndex` is zero-based, counted over table blocks only (skipping
  paragraphs and tables-of-contents).
- `blockIndex` is the absolute position in `body.content` so callers can
  cross-reference results with `docs show-structure`.

Constraints:
- Operates only on top-level body tables.
- Cells must contain only paragraph elements (no nested tables, images,
  or lists). Non-rectangular tables are rejected with a clear error.
- `table-update-cell` requires non-empty `--text`.
- `table-append-row` requires the provided values length to match the
  table's column count exactly.
"""

from __future__ import annotations

import argparse
import json

from suitewright import render
from suitewright.service import build_service


class TableError(SystemExit):
    """Raised when a table cannot be safely manipulated."""


def _collect_tables(doc: dict) -> list[tuple[int, dict]]:
    out = []
    for block_idx, element in enumerate(doc.get("body", {}).get("content", [])):
        if "table" in element:
            out.append((block_idx, element))
    return out


def _cell_text(cell: dict) -> str:
    return render.structural_elements_text(cell.get("content", []), joiner=" ").strip()


def _ensure_rectangular(table: dict) -> None:
    """Reject tables whose cells contain non-paragraph content."""
    for r_idx, row in enumerate(table.get("tableRows", [])):
        for c_idx, cell in enumerate(row.get("tableCells", [])):
            for elem in cell.get("content", []):
                if "paragraph" not in elem:
                    raise TableError(
                        f"Table cell at row={r_idx} col={c_idx} contains "
                        "non-paragraph content (nested table, image, list, etc.); "
                        "suitewright table helpers only support rectangular text-only tables."
                    )


def _table_summary(block_idx: int, table_idx: int, element: dict) -> dict:
    table = element["table"]
    rows = table.get("tableRows", [])
    cells = []
    for row in rows:
        cells.append([_cell_text(cell) for cell in row.get("tableCells", [])])
    return {
        "tableIndex": table_idx,
        "blockIndex": block_idx,
        "startIndex": element.get("startIndex", 0),
        "endIndex": element.get("endIndex", 0),
        "rows": len(rows),
        "cols": max((len(row.get("tableCells", [])) for row in rows), default=0),
        "cells": cells,
    }


def cmd_table_get(args):
    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()
    tables = _collect_tables(doc)

    if args.table is not None:
        if args.table < 0:
            raise SystemExit("--table must be >= 0")
        if args.table >= len(tables):
            raise SystemExit(
                f"--table {args.table} out of range (document has {len(tables)} tables)"
            )
        block_idx, element = tables[args.table]
        print(
            json.dumps(
                {
                    "documentId": args.doc_id,
                    "table": _table_summary(block_idx, args.table, element),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    print(
        json.dumps(
            {
                "documentId": args.doc_id,
                "tables": [
                    _table_summary(block_idx, idx, element)
                    for idx, (block_idx, element) in enumerate(tables)
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _resolve_cell(table: dict, row: int, col: int) -> dict:
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


def cmd_table_update_cell(args):
    if args.table < 0:
        raise SystemExit("--table must be >= 0")
    if args.row < 0:
        raise SystemExit("--row must be >= 0")
    if args.col < 0:
        raise SystemExit("--col must be >= 0")
    if not args.text:
        raise SystemExit("--text must be a non-empty string")

    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()
    tables = _collect_tables(doc)
    if args.table >= len(tables):
        raise SystemExit(f"--table {args.table} out of range (document has {len(tables)} tables)")

    _, element = tables[args.table]
    table = element["table"]
    _ensure_rectangular(table)
    cell = _resolve_cell(table, args.row, args.col)
    start, end = _cell_inner_range(cell)

    requests = []
    if end > start:
        requests.append({"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}})
    requests.append({"insertText": {"location": {"index": start}, "text": args.text}})

    service.documents().batchUpdate(documentId=args.doc_id, body={"requests": requests}).execute()

    print(
        json.dumps(
            {
                "status": "updated",
                "documentId": args.doc_id,
                "tableIndex": args.table,
                "row": args.row,
                "col": args.col,
                "text": args.text,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_table_append_row(args):
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

    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()
    tables = _collect_tables(doc)
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

    last_row = rows[-1]
    last_cell = last_row.get("tableCells", [])[0]
    cell_start = last_cell.get("startIndex", element.get("startIndex", 1))

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
    service.documents().batchUpdate(
        documentId=args.doc_id, body={"requests": [insert_request]}
    ).execute()

    refreshed = service.documents().get(documentId=args.doc_id).execute()
    new_tables = _collect_tables(refreshed)
    new_table = new_tables[args.table][1]["table"]
    new_rows = new_table.get("tableRows", [])
    new_row = new_rows[len(rows)]
    text_requests = []
    for col_idx, value in enumerate(values):
        cell = new_row.get("tableCells", [])[col_idx]
        start, _ = _cell_inner_range(cell)
        text_requests.append({"insertText": {"location": {"index": start}, "text": value}})

    if text_requests:
        # Apply right-to-left to keep earlier indexes stable.
        text_requests.reverse()
        service.documents().batchUpdate(
            documentId=args.doc_id, body={"requests": text_requests}
        ).execute()

    print(
        json.dumps(
            {
                "status": "appended",
                "documentId": args.doc_id,
                "tableIndex": args.table,
                "values": values,
                "columnCount": cols,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    # silence the never-used note for cell_start; included for diagnostics
    _ = cell_start


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("table-get", help="Read tables as 2D cell grids")
    p.add_argument("doc_id")
    p.add_argument(
        "--table", type=int, default=None, help="Zero-based table index (over tables only)"
    )
    p.set_defaults(func=cmd_table_get)

    p = sub.add_parser("table-update-cell", help="Update one visible cell's text")
    p.add_argument("doc_id")
    p.add_argument("--table", type=int, required=True)
    p.add_argument("--row", type=int, required=True)
    p.add_argument("--col", type=int, required=True)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_table_update_cell)

    p = sub.add_parser("table-append-row", help="Append one row of cell values to a table")
    p.add_argument("doc_id")
    p.add_argument("--table", type=int, required=True)
    p.add_argument("--values", required=True, help="JSON array of cell strings")
    p.set_defaults(func=cmd_table_append_row)
