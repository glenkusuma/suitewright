"""Auth subcommands: init / login / check / revoke / install-deps.

Auth files are resolved via suitewright._core.paths (XDG or dev-mode fallback).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from suitewright._core import paths
from suitewright._core.service import SCOPES

REQUIRED_PACKAGES = [
    "google-api-python-client",
    "google-auth-oauthlib",
    "google-auth-httplib2",
]
REDIRECT_URI = "http://localhost:1"


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o600)


def _pending_auth_path() -> Path:
    return paths.resolve("token").parent / "google_oauth_pending.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _token_scopes(payload: dict) -> set[str]:
    raw = payload.get("scopes") or payload.get("scope")
    if not raw:
        return set()
    if isinstance(raw, str):
        return {s.strip() for s in raw.split() if s.strip()}
    return {str(s).strip() for s in raw if str(s).strip()}


def _missing_scopes_from_payload(payload: dict) -> list[str]:
    granted = _token_scopes(payload)
    return sorted(scope for scope in SCOPES if scope not in granted)


def _format_missing(missing: list[str]) -> str:
    bullets = "\n".join(f"  - {s}" for s in missing)
    return (
        "Token is valid but missing required Google Workspace scopes:\n"
        f"{bullets}\n"
        "Run `suitewright auth login` to refresh consent."
    )


def _ensure_deps() -> None:
    try:
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
    except ImportError:
        if not _install_deps_impl():
            sys.exit(1)


def _install_deps_impl() -> bool:
    try:
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401

        return True
    except ImportError:
        pass
    print("Installing Google API dependencies...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *REQUIRED_PACKAGES],
            stdout=subprocess.DEVNULL,
        )
        print("Dependencies installed.")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Failed to install dependencies: {exc}")
        return False


def cmd_init(args):
    src = Path(args.client_secret).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"ERROR: File not found: {src}")
    try:
        data = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit("ERROR: File is not valid JSON.") from exc
    if "installed" not in data and "web" not in data:
        raise SystemExit(
            "ERROR: Not a Google OAuth client secret file (missing 'installed' or 'web' key).\n"
            "Download the correct file from: https://console.google.cloud.google.com/apis/credentials"
        )
    dest = paths.resolve("client_secret")
    _write_private(dest, json.dumps(data, indent=2))
    print(f"OK: Client secret saved to {dest}")


def cmd_login(args):
    client_secret = paths.resolve("client_secret")
    if not client_secret.exists():
        raise SystemExit(
            "ERROR: No client secret stored. "
            "Run `suitewright auth init --client-secret PATH` first."
        )
    _ensure_deps()

    if args.auth_code:
        _exchange_code(args.auth_code)
        return

    if args.auth_url:
        _print_auth_url(client_secret)
        return

    # Interactive: print URL, prompt for code
    _print_auth_url(client_secret)
    print("\nVisit the URL above, complete consent, then paste the redirect URL or code:")
    code = input("> ").strip()
    if not code:
        raise SystemExit("ERROR: No code provided.")
    _exchange_code(code)


def _print_auth_url(client_secret: Path) -> None:
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        str(client_secret),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        autogenerate_code_verifier=True,
    )
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    pending = _pending_auth_path()
    _write_private(
        pending,
        json.dumps(
            {
                "state": state,
                "code_verifier": flow.code_verifier,
                "redirect_uri": REDIRECT_URI,
            },
            indent=2,
        ),
    )
    print(auth_url)


def _extract_code_and_state(code_or_url: str) -> tuple[str, str | None]:
    if not code_or_url.startswith("http"):
        return code_or_url, None
    parsed = urlparse(code_or_url)
    params = parse_qs(parsed.query)
    if "code" not in params:
        raise SystemExit("ERROR: No 'code' parameter found in URL.")
    state = params.get("state", [None])[0]
    return params["code"][0], state


def _exchange_code(code_or_url: str) -> None:
    pending_path = _pending_auth_path()
    if not pending_path.exists():
        raise SystemExit("ERROR: No pending OAuth session. Run `suitewright auth login` first.")
    try:
        pending = json.loads(pending_path.read_text())
    except Exception as exc:
        raise SystemExit(f"ERROR: Could not read pending OAuth session: {exc}") from exc
    if not pending.get("state") or not pending.get("code_verifier"):
        raise SystemExit("ERROR: Pending OAuth session is missing PKCE data. Run login again.")

    from google_auth_oauthlib.flow import Flow

    code, returned_state = _extract_code_and_state(code_or_url)
    if returned_state and returned_state != pending["state"]:
        raise SystemExit("ERROR: OAuth state mismatch. Run login again.")

    flow = Flow.from_client_secrets_file(
        str(paths.resolve("client_secret")),
        scopes=SCOPES,
        redirect_uri=pending.get("redirect_uri", REDIRECT_URI),
        state=pending["state"],
        code_verifier=pending["code_verifier"],
    )
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise SystemExit(f"ERROR: Token exchange failed: {exc}") from exc

    token_payload = json.loads(flow.credentials.to_json())
    missing = _missing_scopes_from_payload(token_payload)
    if missing:
        raise SystemExit(f"ERROR: Refusing to save incomplete token.\n{_format_missing(missing)}")

    token_path = paths.resolve("token")
    _write_private(token_path, json.dumps(token_payload, indent=2))
    pending_path.unlink(missing_ok=True)
    print(f"OK: Authenticated. Token saved to {token_path}")


def cmd_check(args):
    info = paths.describe()
    token_path = paths.resolve("token")

    if not token_path.exists():
        print(json.dumps({**info, "status": "NOT_AUTHENTICATED"}, indent=2))
        sys.exit(1)

    _ensure_deps()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception as exc:
        print(json.dumps({**info, "status": "TOKEN_CORRUPT", "error": str(exc)}, indent=2))
        sys.exit(1)

    payload = _load_json(token_path)

    if creds.valid:
        missing = _missing_scopes_from_payload(payload)
        if missing:
            out = {**info, "status": "AUTH_SCOPE_MISMATCH", "missingScopes": missing}
            print(json.dumps(out, indent=2))
            sys.exit(1)
        print(json.dumps({**info, "status": "AUTHENTICATED"}, indent=2))
        return

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _write_private(token_path, creds.to_json())
            missing = _missing_scopes_from_payload(_load_json(token_path))
            if missing:
                out = {**info, "status": "AUTH_SCOPE_MISMATCH", "missingScopes": missing}
                print(json.dumps(out, indent=2))
                sys.exit(1)
            out = {**info, "status": "AUTHENTICATED", "refreshed": True}
            print(json.dumps(out, indent=2))
            return
        except Exception as exc:
            print(json.dumps({**info, "status": "REFRESH_FAILED", "error": str(exc)}, indent=2))
            sys.exit(1)

    print(json.dumps({**info, "status": "TOKEN_INVALID"}, indent=2))
    sys.exit(1)


def cmd_revoke(args):
    token_path = paths.resolve("token")
    if not token_path.exists():
        print("No token to revoke.")
        return

    _ensure_deps()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        urllib.request.urlopen(  # nosec B310
            "https://oauth2.googleapis.com/revoke?token=" + creds.token,
            data=b"",
            timeout=10,
        )
    except Exception:
        pass

    token_path.unlink(missing_ok=True)
    _pending_auth_path().unlink(missing_ok=True)
    print("OK: Token revoked and deleted.")


def cmd_install_deps(args):
    print(
        "warning: `auth install-deps` is deprecated; "
        "`pip install suitewright` already installs all required packages.",
        file=sys.stderr,
    )
    sys.exit(0 if _install_deps_impl() else 1)


def register(subparsers: argparse._SubParsersAction) -> None:
    auth = subparsers.add_parser("auth", help="Auth setup and status")
    sub = auth.add_subparsers(dest="action", required=True)

    p = sub.add_parser("init", help="Store an OAuth client secret file")
    p.add_argument("--client-secret", required=True, metavar="PATH")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser(
        "login",
        help="Complete OAuth consent (interactive; use --auth-url/--auth-code for headless)",
    )
    p.add_argument(
        "--auth-url",
        action="store_true",
        help="Print the OAuth URL only (headless step 1)",
    )
    p.add_argument(
        "--auth-code",
        default="",
        metavar="CODE_OR_URL",
        help="Exchange an auth code or redirect URL (headless step 2)",
    )
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("check", help="Check auth status and print path resolution info")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("revoke", help="Revoke and delete the stored token")
    p.set_defaults(func=cmd_revoke)

    p = sub.add_parser(
        "install-deps",
        help="[deprecated] Install Google API packages (no-op when installed via pip)",
    )
    p.set_defaults(func=cmd_install_deps)
