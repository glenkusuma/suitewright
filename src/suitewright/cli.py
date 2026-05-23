"""suitewright CLI — top-level argparse dispatch.

Each service module exposes a `register(subparsers)` function that adds
its subcommand tree. This module builds the root parser, calls each
register(), and dispatches to the selected handler.
"""

from __future__ import annotations

import argparse
import sys

from suitewright import __version__, calendar, contacts, drive, gmail, sheets
from suitewright._core import auth
from suitewright.docs import register as register_docs
from suitewright.forms import register as register_forms


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suitewright",
        description="Portable Google Workspace CLI for humans and agents.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"suitewright {__version__}",
    )

    sub = parser.add_subparsers(dest="service", required=True)

    auth.register(sub)
    gmail.register(sub)
    calendar.register(sub)
    drive.register(sub)
    contacts.register(sub)
    sheets.register(sub)
    register_docs(sub)
    register_forms(sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        args.func(args)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
