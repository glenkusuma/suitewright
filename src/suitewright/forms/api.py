"""Forms direct-API subcommands (list/get/create/update)."""

from __future__ import annotations

import argparse
import json

from suitewright._core.service import build_service


def cmd_list(args):
    service = build_service("drive", "v3")
    query = "mimeType='application/vnd.google-apps.form' and trashed=false"
    if args.query:
        query = f"({query}) and ({args.query})"
    results = (
        service.files()
        .list(
            q=query,
            pageSize=args.max,
            fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        )
        .execute()
    )
    print(json.dumps(results.get("files", []), indent=2, ensure_ascii=False))


def cmd_get(args):
    service = build_service("forms", "v1")
    form = service.forms().get(formId=args.form_id).execute()
    print(json.dumps(form, indent=2, ensure_ascii=False))


def cmd_create(args):
    service = build_service("forms", "v1")
    body = {"info": {"title": args.title}}
    if args.document_title:
        body["info"]["documentTitle"] = args.document_title
    result = service.forms().create(body=body).execute()
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_update(args):
    service = build_service("forms", "v1")
    payload = {"requests": json.loads(args.requests)}
    if args.include_form_in_response:
        payload["includeFormInResponse"] = True
    result = service.forms().batchUpdate(formId=args.form_id, body=payload).execute()
    print(json.dumps(result, indent=2, ensure_ascii=False))


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("list", help="List forms via Drive")
    p.add_argument("--max", type=int, default=25)
    p.add_argument("--query", default="", help="Optional Drive query filter")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("get", help="Fetch a form definition")
    p.add_argument("form_id")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("create", help="Create a new form")
    p.add_argument("--title", required=True)
    p.add_argument("--document-title", default="", help="Optional Drive document title")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("update", help="Send a Forms API batchUpdate")
    p.add_argument("form_id")
    p.add_argument("--requests", required=True, help="JSON list of Forms API batchUpdate requests")
    p.add_argument("--include-form-in-response", action="store_true")
    p.set_defaults(func=cmd_update)
