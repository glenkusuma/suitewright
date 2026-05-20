"""Docs basic commands: get/show-structure/create/append/replace/update.

The dry-run path on `docs update` and the request-loading helpers are
shared with `docs.semantic`, `docs.tables`, and `docs.plan`, so they live
in this module as the canonical source.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from suitewright import render
from suitewright.service import build_service


def load_docs_requests(args) -> list[dict]:
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
    summary = []
    for index, request in enumerate(requests):
        if isinstance(request, dict) and request:
            kind = next(iter(request.keys()))
        else:
            kind = "unknown"
        summary.append({"index": index, "kind": kind})
    return summary


def cmd_get(args):
    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()
    print(
        json.dumps(
            {
                "title": doc.get("title", ""),
                "documentId": doc.get("documentId", ""),
                "body": render.structural_elements_text(doc.get("body", {}).get("content", [])),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_show_structure(args):
    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()
    blocks = []
    summary = {"paragraphs": 0, "tables": 0, "tableOfContents": 0}

    for index, element in enumerate(doc.get("body", {}).get("content", [])):
        block = render.show_structure_block(element, index, full_text=args.full_text)
        if not block:
            continue
        if block["kind"] == "paragraph":
            summary["paragraphs"] += 1
        elif block["kind"] == "table":
            summary["tables"] += 1
        elif block["kind"] == "tableOfContents":
            summary["tableOfContents"] += 1
        blocks.append(block)

    print(
        json.dumps(
            {
                "documentId": doc.get("documentId", args.doc_id),
                "title": doc.get("title", ""),
                "summary": summary,
                "blocks": blocks,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_create(args):
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


def cmd_append(args):
    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()
    end_index = max(1, render.document_end_index(doc) - 1)

    service.documents().batchUpdate(
        documentId=args.doc_id,
        body={"requests": [{"insertText": {"location": {"index": end_index}, "text": args.text}}]},
    ).execute()

    print(
        json.dumps(
            {
                "status": "appended",
                "documentId": args.doc_id,
                "inserted_at": end_index,
                "characters": len(args.text),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_replace(args):
    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()
    end_index = max(1, render.document_end_index(doc) - 1)

    requests = []
    if end_index > 1:
        requests.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index}}})
    if args.text:
        requests.append({"insertText": {"location": {"index": 1}, "text": args.text}})

    service.documents().batchUpdate(documentId=args.doc_id, body={"requests": requests}).execute()
    print(
        json.dumps(
            {
                "status": "replaced",
                "documentId": args.doc_id,
                "characters": len(args.text),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_update(args):
    requests = load_docs_requests(args)
    if args.dry_run:
        summary = summarize_docs_requests(requests)
        print(
            json.dumps(
                {
                    "documentId": args.doc_id,
                    "dryRun": True,
                    "requestCount": len(requests),
                    "requestKinds": [item["kind"] for item in summary],
                    "requests": summary,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    service = build_service("docs", "v1")
    result = (
        service.documents()
        .batchUpdate(documentId=args.doc_id, body={"requests": requests})
        .execute()
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("get", help="Fetch a document body as plain text")
    p.add_argument("doc_id")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("show-structure", help="Inspect document structure safely")
    p.add_argument("doc_id")
    p.add_argument(
        "--full-text", action="store_true", help="Include full text for supported block kinds"
    )
    p.set_defaults(func=cmd_show_structure)

    p = sub.add_parser("create", help="Create a new document")
    p.add_argument("--title", required=True)
    p.add_argument("--body", default="")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("append", help="Append text at end of document")
    p.add_argument("doc_id")
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_append)

    p = sub.add_parser("replace", help="Replace document body with new text")
    p.add_argument("doc_id")
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_replace)

    p = sub.add_parser("update", help="Send a raw batchUpdate request payload")
    p.add_argument("doc_id")
    p.add_argument("--requests", default="", help="JSON list of Docs API batchUpdate requests")
    p.add_argument(
        "--requests-file", default="", help="Path to JSON file with batchUpdate requests"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize requests without mutating the document",
    )
    p.set_defaults(func=cmd_update)
