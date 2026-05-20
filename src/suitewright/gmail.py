"""Gmail subcommands."""

from __future__ import annotations

import argparse
import base64
import json
from email.mime.text import MIMEText

from suitewright.service import build_service


def cmd_search(args):
    service = build_service("gmail", "v1")
    results = (
        service.users().messages().list(userId="me", q=args.query, maxResults=args.max).execute()
    )
    messages = results.get("messages", [])
    if not messages:
        print("No messages found.")
        return

    output = []
    for msg_meta in messages:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=msg_meta["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            )
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        output.append(
            {
                "id": msg["id"],
                "threadId": msg["threadId"],
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "labels": msg.get("labelIds", []),
            }
        )
    print(json.dumps(output, indent=2, ensure_ascii=False))


def cmd_get(args):
    service = build_service("gmail", "v1")
    msg = service.users().messages().get(userId="me", id=args.message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

    body = ""
    payload = msg.get("payload", {})
    if payload.get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif payload.get("parts"):
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                    "utf-8", errors="replace"
                )
                break
        if not body:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8", errors="replace"
                    )
                    break

    result = {
        "id": msg["id"],
        "threadId": msg["threadId"],
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "labels": msg.get("labelIds", []),
        "body": body,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_send(args):
    service = build_service("gmail", "v1")
    message = MIMEText(args.body, "html" if args.html else "plain")
    message["to"] = args.to
    message["subject"] = args.subject
    if args.cc:
        message["cc"] = args.cc

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {"raw": raw}
    if args.thread_id:
        body["threadId"] = args.thread_id

    result = service.users().messages().send(userId="me", body=body).execute()
    print(
        json.dumps(
            {"status": "sent", "id": result["id"], "threadId": result.get("threadId", "")},
            indent=2,
        )
    )


def cmd_reply(args):
    service = build_service("gmail", "v1")
    original = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=args.message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Message-ID"],
        )
        .execute()
    )
    headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}

    subject = headers.get("Subject", "")
    if not subject.startswith("Re:"):
        subject = f"Re: {subject}"

    message = MIMEText(args.body)
    message["to"] = headers.get("From", "")
    message["subject"] = subject
    if headers.get("Message-ID"):
        message["In-Reply-To"] = headers["Message-ID"]
        message["References"] = headers["Message-ID"]

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {"raw": raw, "threadId": original["threadId"]}
    result = service.users().messages().send(userId="me", body=body).execute()
    print(
        json.dumps(
            {"status": "sent", "id": result["id"], "threadId": result.get("threadId", "")},
            indent=2,
        )
    )


def cmd_labels(args):
    service = build_service("gmail", "v1")
    results = service.users().labels().list(userId="me").execute()
    labels = [
        {"id": lbl["id"], "name": lbl["name"], "type": lbl.get("type", "")}
        for lbl in results.get("labels", [])
    ]
    print(json.dumps(labels, indent=2, ensure_ascii=False))


def cmd_modify(args):
    service = build_service("gmail", "v1")
    body = {}
    if args.add_labels:
        body["addLabelIds"] = args.add_labels.split(",")
    if args.remove_labels:
        body["removeLabelIds"] = args.remove_labels.split(",")
    result = service.users().messages().modify(userId="me", id=args.message_id, body=body).execute()
    print(
        json.dumps(
            {"id": result["id"], "labels": result.get("labelIds", [])},
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_trash(args):
    service = build_service("gmail", "v1")
    result = service.users().messages().trash(userId="me", id=args.message_id).execute()
    print(
        json.dumps(
            {
                "status": "trashed",
                "id": result["id"],
                "threadId": result.get("threadId", ""),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def register(subparsers: argparse._SubParsersAction) -> None:
    gmail = subparsers.add_parser("gmail", help="Gmail commands")
    sub = gmail.add_subparsers(dest="action", required=True)

    p = sub.add_parser("search", help="Search messages")
    p.add_argument("query", help="Gmail search query (e.g. 'is:unread')")
    p.add_argument("--max", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("get", help="Fetch one message in full")
    p.add_argument("message_id")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("send", help="Send a new message")
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--cc", default="")
    p.add_argument("--html", action="store_true", help="Send body as HTML")
    p.add_argument("--thread-id", default="", help="Thread ID for threading")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("reply", help="Reply to an existing message")
    p.add_argument("message_id", help="Message ID to reply to")
    p.add_argument("--body", required=True)
    p.set_defaults(func=cmd_reply)

    p = sub.add_parser("labels", help="List labels")
    p.set_defaults(func=cmd_labels)

    p = sub.add_parser("modify", help="Add or remove labels on a message")
    p.add_argument("message_id")
    p.add_argument("--add-labels", default="", help="Comma-separated label IDs to add")
    p.add_argument("--remove-labels", default="", help="Comma-separated label IDs to remove")
    p.set_defaults(func=cmd_modify)

    p = sub.add_parser("trash", help="Move a message to trash")
    p.add_argument("message_id", help="Message ID to move to trash")
    p.set_defaults(func=cmd_trash)
