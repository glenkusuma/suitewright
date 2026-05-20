"""Google API credential loading and service factory.

Reads the OAuth token via :func:`suitewright.paths.resolve("token")` and
returns a refreshed Credentials object suitable for any
googleapiclient.discovery.build call.
"""

from __future__ import annotations

import json
import sys

from suitewright import paths

REQUIRED_SCOPE_HINT = "Run `suitewright auth login` to refresh consent for missing scopes."

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/forms.body",
]


def _write_private_token(content: str) -> None:
    token_path = paths.resolve("token")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(content)
    token_path.chmod(0o600)


def _load_token_payload() -> dict:
    try:
        return json.loads(paths.resolve("token").read_text())
    except Exception:
        return {}


def _token_scopes() -> set[str]:
    payload = _load_token_payload()
    raw = payload.get("scopes") or payload.get("scope")
    if not raw:
        return set()
    if isinstance(raw, str):
        return {s.strip() for s in raw.split() if s.strip()}
    return {str(s).strip() for s in raw if str(s).strip()}


def missing_scopes() -> list[str]:
    granted = _token_scopes()
    return sorted(scope for scope in SCOPES if scope not in granted)


def get_credentials():
    """Load and refresh credentials from the resolved token path."""
    token_path = paths.resolve("token")
    if not token_path.exists():
        print("Not authenticated. Run:", file=sys.stderr)
        print("  suitewright auth login", file=sys.stderr)
        sys.exit(1)

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _write_private_token(creds.to_json())
    if not creds.valid:
        print("Token is invalid. Run `suitewright auth login`.", file=sys.stderr)
        sys.exit(1)

    missing = missing_scopes()
    if missing:
        print(
            "Token is valid but missing Google Workspace scopes required by suitewright.",
            file=sys.stderr,
        )
        for scope in missing:
            print(f"  - {scope}", file=sys.stderr)
        print(REQUIRED_SCOPE_HINT, file=sys.stderr)
        sys.exit(1)
    return creds


def build_service(api: str, version: str):
    from googleapiclient.discovery import build

    return build(api, version, credentials=get_credentials())
