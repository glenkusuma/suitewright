"""Docs plan command: build an inspectable request-plan artifact.

Captures the live document's current structure, the request summary, and
the original request list — without mutating the document. Replay is
intentionally deferred until the artifact format proves stable.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from suitewright import render
from suitewright.docs.basic import load_docs_requests, summarize_docs_requests
from suitewright.service import build_service

PLAN_VERSION = "1"


def cmd_plan(args):
    if not args.requests_file:
        raise SystemExit("--requests-file is required for `docs plan`")
    args.requests = ""

    requests = load_docs_requests(args)
    summary_entries = summarize_docs_requests(requests)

    service = build_service("docs", "v1")
    doc = service.documents().get(documentId=args.doc_id).execute()

    blocks = []
    structure_summary = {"paragraphs": 0, "tables": 0, "tableOfContents": 0}
    for index, element in enumerate(doc.get("body", {}).get("content", [])):
        block = render.show_structure_block(element, index, full_text=False)
        if not block:
            continue
        if block["kind"] == "paragraph":
            structure_summary["paragraphs"] += 1
        elif block["kind"] == "table":
            structure_summary["tables"] += 1
        elif block["kind"] == "tableOfContents":
            structure_summary["tableOfContents"] += 1
        blocks.append(block)

    plan = {
        "version": PLAN_VERSION,
        "documentId": doc.get("documentId", args.doc_id),
        "createdAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": {"path": str(Path(args.requests_file).resolve())},
        "summary": {
            "requestCount": len(requests),
            "requestKinds": [item["kind"] for item in summary_entries],
        },
        "preflight": {
            "documentTitle": doc.get("title", ""),
            "structureSummary": structure_summary,
            "blocks": blocks,
        },
        "requests": requests,
    }
    print(json.dumps(plan, indent=2, ensure_ascii=False))


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "plan",
        help="Build a request-plan artifact from a batchUpdate file (no mutation)",
    )
    p.add_argument("doc_id")
    p.add_argument(
        "--requests-file",
        required=True,
        help="Path to JSON file with a list of Docs API batchUpdate requests",
    )
    p.set_defaults(func=cmd_plan)
