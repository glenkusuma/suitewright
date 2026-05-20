"""docs subcommand registration.

Each Docs command module exposes a `register(subparsers)` function.
This module is the single entry-point that the top-level CLI calls into.
"""

from __future__ import annotations

import argparse

from suitewright.docs import basic, comments, plan, semantic, tables, templates


def register(subparsers: argparse._SubParsersAction) -> None:
    docs = subparsers.add_parser("docs", help="Docs commands")
    sub = docs.add_subparsers(dest="action", required=True)

    basic.register(sub)
    templates.register(sub)
    semantic.register(sub)
    comments.register(sub)
    tables.register(sub)
    plan.register(sub)
