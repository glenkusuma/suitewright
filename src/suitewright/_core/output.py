"""Shared JSON output and structured error helpers."""

from __future__ import annotations

import json
import sys


def emit_json(data: dict | list, *, compact: bool = False) -> None:
    """Print JSON to stdout. Used by all command handlers."""
    if compact:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def emit_text(text: str) -> None:
    """Print plain text to stdout (for commands like `query get`)."""
    print(text, end="")


def error_exit(status: str, code: str, message: str, **context) -> None:
    """Print structured JSON error to stderr and exit with code 1.

    Usage:
        error_exit("stale", "REVISION_MISMATCH", "Document changed.",
                   cachedRevision="abc", liveRevision="def")
    """
    payload = {"status": status, "code": code, "message": message, **context}
    print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(1)


def warn(message: str, **context) -> None:
    """Print structured JSON warning to stderr (non-fatal)."""
    payload = {"warning": message, **context}
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
