"""docs subcommand registration — grouped CLI tree.

Organizes docs commands into logical groups:
- cache: Cache lifecycle (fetch, show, validate, update)
- query: Local inspection (operates on cache, zero API calls)
- mutate: Write operations (validates cache + auto-refreshes)
- table: Table read helpers (read-only get)
- Standalone: create, plan, request-template, comments
"""

from __future__ import annotations

import argparse
import json

from suitewright.docs import comments, mutate, plan, query, state, tables, templates


def _cmd_create(args) -> None:
    """Create a new Google Doc, optionally inserting initial body text."""
    from suitewright._core.service import build_service

    service = build_service("docs", "v1")
    doc = service.documents().create(body={"title": args.title}).execute()

    inserted = 0
    if args.body:
        service.documents().batchUpdate(
            documentId=doc["documentId"],
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": args.body}}]},
        ).execute()
        inserted = len(args.body)

    print(
        json.dumps(
            {
                "status": "created",
                "documentId": doc["documentId"],
                "title": doc.get("title", args.title),
                "url": f"https://docs.google.com/document/d/{doc['documentId']}/edit",
                "characters": inserted,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def register(subparsers: argparse._SubParsersAction) -> None:
    docs = subparsers.add_parser("docs", help="Docs commands")
    sub = docs.add_subparsers(dest="action", required=True)

    # -----------------------------------------------------------------------
    # Cache lifecycle group: docs cache {fetch, show, validate, update}
    # Workflow: fetch → validate → (query) → update
    # -----------------------------------------------------------------------
    cache_parser = sub.add_parser(
        "cache",
        help="Cache lifecycle (fetch → validate → update)",
        description=(
            "Cache lifecycle commands for Google Docs.\n\n"
            "Workflow: fetch → validate → (query) → update\n\n"
            "The cache stores the full API response locally so queries "
            "and validations run without network calls. Use 'docs cache fetch' "
            "to pull a fresh copy before inspecting or mutating."
        ),
    )
    cache_sub = cache_parser.add_subparsers(dest="cache_action", required=True)
    state.register(cache_sub)

    # -----------------------------------------------------------------------
    # Query group: docs query {structure, get, list-headings, ...}
    # All query commands operate on the local cache — no API calls.
    # -----------------------------------------------------------------------
    query_parser = sub.add_parser(
        "query",
        help="Local inspection (operates on cache, no API calls)",
        description=(
            "Local inspection commands that operate on the cached document.\n\n"
            "All query commands require 'docs cache fetch' first — they read "
            "from the local JSON cache and make zero API calls.\n\n"
            "Example: docs cache fetch DOC_ID && docs query list-headings DOC_ID"
        ),
    )
    query_sub = query_parser.add_subparsers(dest="query_action", required=True)
    query.register(query_sub)

    # -----------------------------------------------------------------------
    # Mutate group: docs mutate {append, replace, replace-all, ...}
    # All mutate commands validate cache freshness and auto-refresh after success.
    # -----------------------------------------------------------------------
    mutate_parser = sub.add_parser(
        "mutate",
        help="Write operations (validates cache + auto-refreshes)",
        description=(
            "Semantic write helpers for Google Docs.\n\n"
            "All mutate commands validate cache freshness before executing "
            "and automatically refresh the local cache after success. "
            "Use --dry-run to preview changes without mutating.\n\n"
            "Example: docs cache fetch DOC_ID && docs mutate replace-all DOC_ID "
            "--find 'old' --replace 'new'"
        ),
    )
    mutate_sub = mutate_parser.add_subparsers(dest="mutate_action", required=True)
    mutate.register(mutate_sub)

    # -----------------------------------------------------------------------
    # Table read group: docs table {get}
    # Read-only table helpers operating on cache.
    # -----------------------------------------------------------------------
    table_parser = sub.add_parser(
        "table",
        help="Table read helpers (read-only)",
        description=(
            "Read-only table helpers for cached Google Docs.\n\n"
            "Reads table data as structured 2D cell grids from the local cache. "
            "Requires 'docs cache fetch' first."
        ),
    )
    table_sub = table_parser.add_subparsers(dest="table_action", required=True)
    tables.register(table_sub)

    # -----------------------------------------------------------------------
    # Standalone commands
    # -----------------------------------------------------------------------

    # docs plan
    plan.register(sub)

    # docs request-template
    templates.register(sub)

    # docs comments {list, get, reply}
    comments.register(sub)

    # docs create
    create_parser = sub.add_parser("create", help="Create a new document")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--body", default="")
    create_parser.set_defaults(func=_cmd_create)
