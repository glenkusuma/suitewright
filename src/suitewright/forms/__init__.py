"""forms subcommand registration."""

from __future__ import annotations

import argparse

from suitewright.forms import api, query, state


def register(subparsers: argparse._SubParsersAction) -> None:
    forms = subparsers.add_parser("forms", help="Google Forms commands")
    sub = forms.add_subparsers(dest="action", required=True)

    # Direct API commands: list, get, create, update
    api.register(sub)

    # State lifecycle commands: fetch, show-cache, validate, cache-update
    state.register(sub)

    # Query sub-subcommand group
    q_parser = sub.add_parser("query", help="Cache-first query helpers")
    q_sub = q_parser.add_subparsers(dest="query_action", required=True)
    query.register(q_sub)
