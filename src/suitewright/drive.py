"""Drive subcommands: search / get / upload / create-folder / download / share / delete."""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
from pathlib import Path

from suitewright._core.service import build_service

VALID_SHARE_ROLES = {"reader", "commenter", "writer"}


def cmd_search(args):
    service = build_service("drive", "v3")
    query = f"fullText contains '{args.query}'" if not args.raw_query else args.query
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
    service = build_service("drive", "v3")
    file = (
        service.files()
        .get(
            fileId=args.file_id,
            fields="id,name,mimeType,modifiedTime,size,webViewLink,parents,owners(displayName)",
        )
        .execute()
    )

    out: dict = {
        "id": file["id"],
        "name": file.get("name", ""),
        "mimeType": file.get("mimeType", ""),
    }
    if "modifiedTime" in file:
        out["modifiedTime"] = file["modifiedTime"]
    if "size" in file:
        out["size"] = file["size"]
    if "webViewLink" in file:
        out["webViewLink"] = file["webViewLink"]
    if file.get("parents"):
        out["parents"] = file["parents"]
    if file.get("owners"):
        out["owners"] = [o.get("displayName", "") for o in file["owners"] if o.get("displayName")]
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_upload(args):
    from googleapiclient.http import MediaFileUpload

    path = Path(args.path).expanduser()
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    if not path.is_file():
        raise SystemExit(f"Not a regular file: {path}")

    mime, _ = mimetypes.guess_type(str(path))
    media = MediaFileUpload(str(path), mimetype=mime, resumable=False)

    name = args.name or path.name
    body: dict = {"name": name}
    if args.parent:
        body["parents"] = [args.parent]

    service = build_service("drive", "v3")
    result = (
        service.files()
        .create(
            body=body,
            media_body=media,
            fields="id,name,mimeType,webViewLink",
        )
        .execute()
    )
    out = {
        "status": "uploaded",
        "id": result["id"],
        "name": result.get("name", name),
        "mimeType": result.get("mimeType", mime or ""),
    }
    if result.get("webViewLink"):
        out["webViewLink"] = result["webViewLink"]
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_create_folder(args):
    service = build_service("drive", "v3")
    body = {"name": args.name, "mimeType": "application/vnd.google-apps.folder"}
    if args.parent:
        body["parents"] = [args.parent]
    result = service.files().create(body=body, fields="id,name,webViewLink").execute()
    out = {"status": "created", "id": result["id"], "name": result.get("name", args.name)}
    if result.get("webViewLink"):
        out["webViewLink"] = result["webViewLink"]
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _is_native_google_mime(mime: str) -> bool:
    return mime.startswith("application/vnd.google-apps.")


def cmd_download(args):
    from googleapiclient.http import MediaIoBaseDownload

    service = build_service("drive", "v3")
    metadata = service.files().get(fileId=args.file_id, fields="id,name,mimeType").execute()
    mime = metadata.get("mimeType", "")
    name = metadata.get("name", args.file_id)

    if _is_native_google_mime(mime):
        if not args.export_mime:
            raise SystemExit(
                f"File '{name}' has native Google MIME type {mime!r}; "
                "pass --export-mime to choose an export format "
                "(for example: application/pdf)."
            )
        request = service.files().export_media(fileId=args.file_id, mimeType=args.export_mime)
        effective_mime = args.export_mime
    else:
        request = service.files().get_media(fileId=args.file_id)
        effective_mime = mime

    output = Path(args.output).expanduser() if args.output else Path(name)
    output.parent.mkdir(parents=True, exist_ok=True)

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    output.write_bytes(buffer.getvalue())

    print(
        json.dumps(
            {
                "status": "downloaded",
                "id": metadata["id"],
                "name": name,
                "path": str(output.resolve()),
                "mimeType": effective_mime,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_share(args):
    if args.role not in VALID_SHARE_ROLES:
        raise SystemExit(f"Invalid --role {args.role!r}; choose one of {sorted(VALID_SHARE_ROLES)}")

    service = build_service("drive", "v3")
    permission = {"type": "user", "emailAddress": args.email, "role": args.role}
    result = (
        service.permissions()
        .create(
            fileId=args.file_id,
            body=permission,
            sendNotificationEmail=bool(args.notify),
            fields="id",
        )
        .execute()
    )
    print(
        json.dumps(
            {
                "status": "shared",
                "permissionId": result["id"],
                "fileId": args.file_id,
                "role": args.role,
                "type": "user",
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_delete(args):
    service = build_service("drive", "v3")
    if args.permanent:
        service.files().delete(fileId=args.file_id).execute()
        print(
            json.dumps(
                {"status": "deleted", "fileId": args.file_id, "permanent": True},
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    result = (
        service.files()
        .update(fileId=args.file_id, body={"trashed": True}, fields="id, trashed")
        .execute()
    )
    print(
        json.dumps(
            {"status": "trashed", "fileId": result["id"], "permanent": False},
            indent=2,
            ensure_ascii=False,
        )
    )


def register(subparsers: argparse._SubParsersAction) -> None:
    drv = subparsers.add_parser("drive", help="Drive commands")
    sub = drv.add_subparsers(dest="action", required=True)

    p = sub.add_parser("search", help="Search files")
    p.add_argument("query")
    p.add_argument("--max", type=int, default=10)
    p.add_argument("--raw-query", action="store_true", help="Use query as raw Drive API query")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("get", help="Fetch normalized metadata for one file")
    p.add_argument("file_id")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("upload", help="Upload a local file to Drive")
    p.add_argument("path", help="Local file path")
    p.add_argument("--name", default="", help="Optional display name override")
    p.add_argument("--parent", default="", help="Optional parent folder ID")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("create-folder", help="Create a Drive folder")
    p.add_argument("name")
    p.add_argument("--parent", default="", help="Optional parent folder ID")
    p.set_defaults(func=cmd_create_folder)

    p = sub.add_parser(
        "download",
        help="Download a Drive file (or export a native Google file with --export-mime)",
    )
    p.add_argument("file_id")
    p.add_argument("--output", default="", help="Local output path")
    p.add_argument(
        "--export-mime",
        default="",
        help="Required for native Google files (e.g. application/pdf, text/plain)",
    )
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("share", help="Share a Drive file with a user")
    p.add_argument("file_id")
    p.add_argument("--email", required=True)
    p.add_argument(
        "--role",
        required=True,
        choices=sorted(VALID_SHARE_ROLES),
        help="Permission role (reader, commenter, writer)",
    )
    p.add_argument(
        "--notify", action="store_true", help="Send the standard Drive notification email"
    )
    p.set_defaults(func=cmd_share)

    p = sub.add_parser(
        "delete",
        help="Move a file to trash (default) or permanently delete with --permanent",
    )
    p.add_argument("file_id", help="Drive file ID to delete")
    p.add_argument(
        "--permanent",
        action="store_true",
        help="Permanently delete instead of moving to trash",
    )
    p.set_defaults(func=cmd_delete)
