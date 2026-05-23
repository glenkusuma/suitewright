"""Sheets subcommands."""

from __future__ import annotations

import argparse
import json

from suitewright._core.service import build_service


def cmd_get(args):
    service = build_service("sheets", "v4")
    result = (
        service.spreadsheets().values().get(spreadsheetId=args.sheet_id, range=args.range).execute()
    )
    print(json.dumps(result.get("values", []), indent=2, ensure_ascii=False))


def cmd_update(args):
    service = build_service("sheets", "v4")
    values = json.loads(args.values)
    body = {"values": values}
    result = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=args.sheet_id,
            range=args.range,
            valueInputOption="USER_ENTERED",
            body=body,
        )
        .execute()
    )
    print(
        json.dumps(
            {
                "updatedCells": result.get("updatedCells", 0),
                "updatedRange": result.get("updatedRange", ""),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_append(args):
    service = build_service("sheets", "v4")
    values = json.loads(args.values)
    body = {"values": values}
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=args.sheet_id,
            range=args.range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
    )
    print(
        json.dumps(
            {"updatedCells": result.get("updates", {}).get("updatedCells", 0)},
            indent=2,
            ensure_ascii=False,
        )
    )


def register(subparsers: argparse._SubParsersAction) -> None:
    sh = subparsers.add_parser("sheets", help="Sheets commands")
    sub = sh.add_subparsers(dest="action", required=True)

    p = sub.add_parser("get", help="Read a range")
    p.add_argument("sheet_id")
    p.add_argument("range")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("update", help="Update a range")
    p.add_argument("sheet_id")
    p.add_argument("range")
    p.add_argument("--values", required=True, help="JSON array of arrays")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("append", help="Append rows to a range")
    p.add_argument("sheet_id")
    p.add_argument("range")
    p.add_argument("--values", required=True, help="JSON array of arrays")
    p.set_defaults(func=cmd_append)
