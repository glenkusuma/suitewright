"""Calendar subcommands."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta

from suitewright._core.service import build_service


def cmd_list(args):
    service = build_service("calendar", "v3")
    now = datetime.now(UTC)
    time_min = args.start or now.isoformat()
    time_max = args.end or (now + timedelta(days=7)).isoformat()

    results = (
        service.events()
        .list(
            calendarId=args.calendar,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=args.max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = []
    for e in results.get("items", []):
        events.append(
            {
                "id": e["id"],
                "summary": e.get("summary", "(no title)"),
                "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
                "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
                "location": e.get("location", ""),
                "description": e.get("description", ""),
                "status": e.get("status", ""),
                "htmlLink": e.get("htmlLink", ""),
            }
        )
    print(json.dumps(events, indent=2, ensure_ascii=False))


def cmd_create(args):
    service = build_service("calendar", "v3")
    event = {
        "summary": args.summary,
        "start": {"dateTime": args.start},
        "end": {"dateTime": args.end},
    }
    if args.location:
        event["location"] = args.location
    if args.description:
        event["description"] = args.description
    if args.attendees:
        event["attendees"] = [{"email": e.strip()} for e in args.attendees.split(",") if e.strip()]

    result = service.events().insert(calendarId=args.calendar, body=event).execute()
    print(
        json.dumps(
            {
                "status": "created",
                "id": result["id"],
                "summary": result.get("summary", ""),
                "htmlLink": result.get("htmlLink", ""),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_delete(args):
    service = build_service("calendar", "v3")
    service.events().delete(calendarId=args.calendar, eventId=args.event_id).execute()
    print(json.dumps({"status": "deleted", "eventId": args.event_id}, indent=2, ensure_ascii=False))


def register(subparsers: argparse._SubParsersAction) -> None:
    cal = subparsers.add_parser("calendar", help="Calendar commands")
    sub = cal.add_subparsers(dest="action", required=True)

    p = sub.add_parser("list", help="List upcoming events")
    p.add_argument("--start", default="", help="Start time (ISO 8601)")
    p.add_argument("--end", default="", help="End time (ISO 8601)")
    p.add_argument("--max", type=int, default=25)
    p.add_argument("--calendar", required=True, help="Explicit calendar ID")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("create", help="Create a new event")
    p.add_argument("--summary", required=True)
    p.add_argument("--start", required=True, help="Start (ISO 8601 with timezone)")
    p.add_argument("--end", required=True, help="End (ISO 8601 with timezone)")
    p.add_argument("--location", default="")
    p.add_argument("--description", default="")
    p.add_argument("--attendees", default="", help="Comma-separated email addresses")
    p.add_argument("--calendar", required=True, help="Explicit calendar ID")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("delete", help="Delete an event")
    p.add_argument("event_id")
    p.add_argument("--calendar", required=True, help="Explicit calendar ID")
    p.set_defaults(func=cmd_delete)
