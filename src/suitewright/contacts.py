"""Contacts subcommands."""

from __future__ import annotations

import argparse
import json

from suitewright.service import build_service


def cmd_list(args):
    service = build_service("people", "v1")
    results = (
        service.people()
        .connections()
        .list(
            resourceName="people/me",
            pageSize=args.max,
            personFields="names,emailAddresses,phoneNumbers",
        )
        .execute()
    )
    contacts = []
    for person in results.get("connections", []):
        names = person.get("names", [{}])
        emails = person.get("emailAddresses", [])
        phones = person.get("phoneNumbers", [])
        contacts.append(
            {
                "name": names[0].get("displayName", "") if names else "",
                "emails": [e.get("value", "") for e in emails],
                "phones": [p.get("value", "") for p in phones],
            }
        )
    print(json.dumps(contacts, indent=2, ensure_ascii=False))


def register(subparsers: argparse._SubParsersAction) -> None:
    con = subparsers.add_parser("contacts", help="Contacts commands")
    sub = con.add_subparsers(dest="action", required=True)
    p = sub.add_parser("list", help="List contacts")
    p.add_argument("--max", type=int, default=50)
    p.set_defaults(func=cmd_list)
