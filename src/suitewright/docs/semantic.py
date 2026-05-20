"""Docs semantic helpers: replace-all / insert-table / insert-image / style-range.

Each helper wraps a small, validated batchUpdate so users do not have to
hand-write the request payload. The request shapes match the templates
emitted by `docs request-template <kind>`.
"""

from __future__ import annotations

import argparse
import json

from suitewright import render
from suitewright.service import build_service


def cmd_replace_all(args):
    if not args.find:
        raise SystemExit("--find must be a non-empty string")

    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()

    changed_blocks = []
    for index, element in enumerate(doc.get("body", {}).get("content", [])):
        block = render.show_structure_block(element, index, full_text=True)
        if not block:
            continue
        text = block.get("text", "")
        if args.find not in text:
            continue
        entry = {
            "blockIndex": index,
            "kind": block.get("kind", ""),
            "startIndex": block.get("startIndex", 0),
            "endIndex": block.get("endIndex", 0),
            "preview": render.compact_preview(text),
        }
        changed_blocks.append(entry)

    request = {
        "replaceAllText": {
            "containsText": {"text": args.find, "matchCase": True},
            "replaceText": args.replace,
        }
    }
    response = (
        service.documents()
        .batchUpdate(documentId=args.doc_id, body={"requests": [request]})
        .execute()
    )

    occurrences = 0
    replies = response.get("replies") or []
    if replies:
        occurrences = replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0)

    print(
        json.dumps(
            {
                "status": "replaced",
                "documentId": args.doc_id,
                "find": args.find,
                "replace": args.replace,
                "matchCase": True,
                "occurrencesChanged": occurrences,
                "changedBlocks": changed_blocks,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_insert_table(args):
    if args.rows <= 0:
        raise SystemExit("--rows must be > 0")
    if args.cols <= 0:
        raise SystemExit("--cols must be > 0")
    if args.index < 1:
        raise SystemExit("--index must be >= 1")

    service = build_service("docs", "v1")
    request = {
        "insertTable": {
            "rows": args.rows,
            "columns": args.cols,
            "location": {"index": args.index},
        }
    }
    service.documents().batchUpdate(documentId=args.doc_id, body={"requests": [request]}).execute()

    print(
        json.dumps(
            {
                "status": "inserted",
                "documentId": args.doc_id,
                "rows": args.rows,
                "cols": args.cols,
                "index": args.index,
                "requestKind": "insertTable",
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_insert_image(args):
    if not args.uri:
        raise SystemExit("--uri must be a non-empty URL")
    if args.index < 1:
        raise SystemExit("--index must be >= 1")

    service = build_service("docs", "v1")
    request = {
        "insertInlineImage": {
            "uri": args.uri,
            "location": {"index": args.index},
        }
    }
    service.documents().batchUpdate(documentId=args.doc_id, body={"requests": [request]}).execute()

    print(
        json.dumps(
            {
                "status": "inserted",
                "documentId": args.doc_id,
                "uri": args.uri,
                "index": args.index,
                "requestKind": "insertInlineImage",
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_style_range(args):
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
    request = {
        "updateTextStyle": {
            "range": {"startIndex": args.start_index, "endIndex": args.end_index},
            "textStyle": text_style,
            "fields": fields_mask,
        }
    }

    service = build_service("docs", "v1")
    service.documents().batchUpdate(documentId=args.doc_id, body={"requests": [request]}).execute()

    print(
        json.dumps(
            {
                "status": "styled",
                "documentId": args.doc_id,
                "startIndex": args.start_index,
                "endIndex": args.end_index,
                "fields": fields_mask,
                "requestKind": "updateTextStyle",
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("replace-all", help="Replace all occurrences of text in a document")
    p.add_argument("doc_id")
    p.add_argument("--find", required=True, help="String to find (matchCase=true)")
    p.add_argument("--replace", required=True, help="Replacement string (may be empty)")
    p.set_defaults(func=cmd_replace_all)

    p = sub.add_parser("insert-table", help="Insert a table at a structural index")
    p.add_argument("doc_id")
    p.add_argument("--rows", type=int, required=True)
    p.add_argument("--cols", type=int, required=True)
    p.add_argument("--index", type=int, required=True)
    p.set_defaults(func=cmd_insert_table)

    p = sub.add_parser("insert-image", help="Insert an inline image at a structural index")
    p.add_argument("doc_id")
    p.add_argument("--uri", required=True, help="Public URL to image")
    p.add_argument("--index", type=int, required=True)
    p.set_defaults(func=cmd_insert_image)

    p = sub.add_parser("style-range", help="Apply a small text-style update to a range")
    p.add_argument("doc_id")
    p.add_argument("--start-index", type=int, required=True)
    p.add_argument("--end-index", type=int, required=True)
    p.add_argument("--bold", action="store_true", help="Set bold=true on the range")
    p.set_defaults(func=cmd_style_range)
