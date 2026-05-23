"""Docs comments helpers: list / get / reply.

Backend: Drive v3 comments/replies APIs (the Docs API does not directly
expose document comments).

The Drive scope in service.SCOPES is sufficient for read paths and reply
creation. Smoke-test reply creation manually before relying on it at scale.
"""

from __future__ import annotations

import argparse
import json

from suitewright._core.service import build_service

COMMENT_FIELDS = (
    "id,content,htmlContent,quotedFileContent(value),"
    "author/displayName,createdTime,modifiedTime,resolved,deleted,anchor,"
    "replies(id,content,htmlContent,author/displayName,createdTime,modifiedTime,deleted)"
)


def _normalize_reply(raw: dict) -> dict:
    out: dict = {}
    if raw.get("id"):
        out["replyId"] = raw["id"]
    if raw.get("content") is not None:
        out["content"] = raw.get("content", "")
    if raw.get("htmlContent"):
        out["htmlContent"] = raw["htmlContent"]
    author = (raw.get("author") or {}).get("displayName")
    if author:
        out["author"] = author
    for key in ("createdTime", "modifiedTime"):
        if raw.get(key):
            out[key] = raw[key]
    if raw.get("deleted") is not None:
        out["deleted"] = bool(raw["deleted"])
    return out


def _normalize_comment(raw: dict, *, include_replies: bool) -> dict:
    out: dict = {}
    if raw.get("id"):
        out["commentId"] = raw["id"]
    if raw.get("content") is not None:
        out["content"] = raw.get("content", "")
    if raw.get("htmlContent"):
        out["htmlContent"] = raw["htmlContent"]
    quoted = (raw.get("quotedFileContent") or {}).get("value")
    if quoted:
        out["quotedFileContent"] = quoted
    author = (raw.get("author") or {}).get("displayName")
    if author:
        out["author"] = author
    for key in ("createdTime", "modifiedTime", "anchor"):
        if raw.get(key):
            out[key] = raw[key]
    if raw.get("resolved") is not None:
        out["resolved"] = bool(raw["resolved"])
    if raw.get("deleted") is not None:
        out["deleted"] = bool(raw["deleted"])

    replies = raw.get("replies") or []
    if include_replies:
        out["replies"] = [_normalize_reply(r) for r in replies]
    else:
        out["replyCount"] = len(replies)
    return out


def cmd_list(args):
    service = build_service("drive", "v3")
    comments = []
    page_token = None
    next_token = ""  # nosec B105

    while True:
        request_kwargs: dict = {
            "fileId": args.doc_id,
            "fields": f"comments({COMMENT_FIELDS}),nextPageToken",
            "pageSize": 100,
        }
        if page_token:
            request_kwargs["pageToken"] = page_token
        response = service.comments().list(**request_kwargs).execute()

        for raw in response.get("comments", []):
            comments.append(_normalize_comment(raw, include_replies=False))

        next_token = response.get("nextPageToken", "")
        if args.all and next_token:
            page_token = next_token
            continue
        break

    payload: dict = {"documentId": args.doc_id, "comments": comments}
    if next_token and not args.all:
        payload["nextPageToken"] = next_token
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_get(args):
    service = build_service("drive", "v3")
    raw = (
        service.comments()
        .get(fileId=args.doc_id, commentId=args.comment_id, fields=COMMENT_FIELDS)
        .execute()
    )
    print(
        json.dumps(
            {
                "documentId": args.doc_id,
                "comment": _normalize_comment(raw, include_replies=True),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_reply(args):
    if not args.text:
        raise SystemExit("--text must be a non-empty string")

    service = build_service("drive", "v3")
    raw = (
        service.replies()
        .create(
            fileId=args.doc_id,
            commentId=args.comment_id,
            body={"content": args.text},
            fields="id,content",
        )
        .execute()
    )
    print(
        json.dumps(
            {
                "status": "replied",
                "documentId": args.doc_id,
                "commentId": args.comment_id,
                "replyId": raw.get("id", ""),
                "content": raw.get("content", args.text),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def register(sub: argparse._SubParsersAction) -> None:
    comments = sub.add_parser("comments", help="Document comments via Drive v3")
    csub = comments.add_subparsers(dest="comments_action", required=True)

    p = csub.add_parser("list", help="List comments on a document")
    p.add_argument("doc_id")
    p.add_argument(
        "--all",
        action="store_true",
        help="Follow nextPageToken until exhausted (default: one page only)",
    )
    p.set_defaults(func=cmd_list)

    p = csub.add_parser("get", help="Fetch one comment with replies inline")
    p.add_argument("doc_id")
    p.add_argument("comment_id")
    p.set_defaults(func=cmd_get)

    p = csub.add_parser("reply", help="Create a reply on an existing comment")
    p.add_argument("doc_id")
    p.add_argument("comment_id")
    p.add_argument("--text", required=True, help="Reply text (non-empty)")
    p.set_defaults(func=cmd_reply)
