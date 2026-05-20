"""docs request-template <kind> commands.

Emits valid starter JSON for common Docs batchUpdate operations.
Templates intentionally stay minimal; richer styling examples live in
the project's reference docs.
"""

from __future__ import annotations

import argparse
import json


def _print(requests: list[dict]) -> None:
    print(json.dumps(requests, indent=2, ensure_ascii=False))


def cmd_replace_all(args):
    _print(
        [
            {
                "replaceAllText": {
                    "containsText": {"text": "FIND_ME", "matchCase": True},
                    "replaceText": "REPLACE_ME",
                }
            }
        ]
    )


def cmd_insert_table(args):
    _print([{"insertTable": {"rows": 2, "columns": 3, "location": {"index": 1}}}])


def cmd_insert_image(args):
    _print(
        [
            {
                "insertInlineImage": {
                    "uri": "https://example.com/image.png",
                    "location": {"index": 1},
                }
            }
        ]
    )


def cmd_style_range(args):
    _print(
        [
            {
                "updateTextStyle": {
                    "range": {"startIndex": 1, "endIndex": 10},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            }
        ]
    )


def register(sub: argparse._SubParsersAction) -> None:
    templates = sub.add_parser(
        "request-template", help="Generate starter Docs batchUpdate request JSON"
    )
    templates_sub = templates.add_subparsers(dest="kind", required=True)

    p = templates_sub.add_parser("replace-all", help="replaceAllText starter request list")
    p.set_defaults(func=cmd_replace_all)

    p = templates_sub.add_parser("insert-table", help="insertTable starter request list")
    p.set_defaults(func=cmd_insert_table)

    p = templates_sub.add_parser("insert-image", help="insertInlineImage starter request list")
    p.set_defaults(func=cmd_insert_image)

    p = templates_sub.add_parser("style-range", help="Minimal updateTextStyle starter request list")
    p.set_defaults(func=cmd_style_range)
