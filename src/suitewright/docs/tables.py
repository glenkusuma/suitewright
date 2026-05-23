"""Docs table read helpers: table get (read-only).

Index model:
- `tableIndex` is zero-based, counted over table blocks only (skipping
  paragraphs and tables-of-contents).
- `blockIndex` is the absolute position in `body.content` so callers can
  cross-reference results with `docs show-structure`.

Constraints:
- Operates only on top-level body tables.
- Cells must contain only paragraph elements (no nested tables, images,
  or lists). Non-rectangular tables are rejected with a clear error.

Write operations (table-update-cell, table-append-row) have moved to
`docs/mutate.py` where they use the guarded_mutate wrapper.
"""

from __future__ import annotations

import argparse

from suitewright._core.cache import CacheStore
from suitewright._core.output import emit_json, error_exit
from suitewright._core.render import structural_elements_text

_cache = CacheStore("docs")


def _collect_tables(doc: dict) -> list[tuple[int, dict]]:
    out = []
    for block_idx, element in enumerate(doc.get("body", {}).get("content", [])):
        if "table" in element:
            out.append((block_idx, element))
    return out


def _cell_text(cell: dict) -> str:
    return structural_elements_text(cell.get("content", []), joiner=" ").strip()


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
    """Read tables from cached document as 2D cell grids."""
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)
    tables = _collect_tables(doc)

    compact = getattr(args, "compact", False)

    if args.table is not None:
        if args.table < 0:
            raise SystemExit("--table must be >= 0")
        if args.table >= len(tables):
            error_exit(
                "error",
                "TABLE_NOT_FOUND",
                f"--table {args.table} out of range (document has {len(tables)} tables)",
                documentId=args.doc_id,
                tableCount=len(tables),
                validRange=f"0-{len(tables) - 1}" if tables else "none",
            )
        block_idx, element = tables[args.table]
        emit_json(
            {
                "documentId": args.doc_id,
                "table": _table_summary(block_idx, args.table, element),
            },
            compact=compact,
        )
        return

    emit_json(
        {
            "documentId": args.doc_id,
            "tables": [
                _table_summary(block_idx, idx, element)
                for idx, (block_idx, element) in enumerate(tables)
            ],
        },
        compact=compact,
    )


def register(sub: argparse._SubParsersAction) -> None:
    """Register the table get subcommand (read-only)."""
    p = sub.add_parser("get", help="Read tables as 2D cell grids from cache")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument(
        "--table", type=int, default=None, help="Zero-based table index (over tables only)"
    )
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_table_get)
