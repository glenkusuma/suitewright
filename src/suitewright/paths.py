"""Path resolution for suitewright auth, cache, and root locations.

Resolution precedence (highest first):

1. Explicit override env vars (mode "env"):
   - SUITEWRIGHT_TOKEN
   - SUITEWRIGHT_CLIENT_SECRET
   - SUITEWRIGHT_CACHE_DIR
   - SUITEWRIGHT_ROOT

2. XDG explicit (mode "xdg") - only when XDG_CONFIG_HOME is explicitly set:
   - $XDG_CONFIG_HOME/suitewright/auth/<file>

3. Dev-mode (mode "dev"):
   - SUITEWRIGHT_AUTH_DIR/<file> (default ../suitewright-auth relative to detected dev root)

4. Default fallback (mode "default"):
   - $HOME/.config/suitewright/auth/<file>
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

Kind = Literal["token", "client_secret", "cache_dir", "root"]

TOKEN_FILENAME = "google_token.json"  # nosec B105
CLIENT_SECRET_FILENAME = "google_client_secret.json"  # nosec B105


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _xdg_cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")


def _read_pyproject_name(pyproject: Path) -> str | None:
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    in_project = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if in_project and line.startswith("name"):
            _, _, value = line.partition("=")
            return value.strip().strip('"').strip("'")
    return None


def _detect_dev_root() -> Path | None:
    """Walk up from CWD looking for suitewright dev root markers.

    Markers checked:
    - .suitewright-dev marker file
    - pyproject.toml with [project].name == "suitewright"

    NOTE: The repo-root auth/ heuristic has been removed (AC1).
    """
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".suitewright-dev").exists():
            return parent
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            name = _read_pyproject_name(pyproject)
            if name == "suitewright":
                return parent
    return None


def _auth_dir() -> Path | None:
    """Resolve the auth directory for dev mode.

    Uses SUITEWRIGHT_AUTH_DIR env var if set, otherwise defaults to
    ../suitewright-auth relative to the detected dev root.
    """
    explicit = os.environ.get("SUITEWRIGHT_AUTH_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    dev_root = _detect_dev_root()
    if dev_root is not None:
        return (dev_root / ".." / "suitewright-auth").resolve()
    return None


def _explicit_root() -> Path | None:
    explicit = os.environ.get("SUITEWRIGHT_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return None


def _has_explicit_xdg() -> bool:
    """Return True if XDG_CONFIG_HOME is explicitly set in the environment."""
    return "XDG_CONFIG_HOME" in os.environ


def resolve(kind: Kind) -> Path:
    """Resolve a path for the given kind using 4-mode precedence.

    Precedence (highest wins):
    1. env: explicit env var overrides (SUITEWRIGHT_TOKEN, etc.)
    2. xdg: $XDG_CONFIG_HOME/suitewright/auth/<file> (only if XDG_CONFIG_HOME is set)
    3. dev: SUITEWRIGHT_AUTH_DIR/<file> (default ../suitewright-auth relative to dev root)
    4. default: $HOME/.config/suitewright/auth/<file>
    """
    if kind == "token":
        # Mode 1: env
        explicit = os.environ.get("SUITEWRIGHT_TOKEN")
        if explicit:
            return Path(explicit).expanduser().resolve()
        root = _explicit_root()
        if root is not None:
            return root / "auth" / TOKEN_FILENAME

        # Mode 2: xdg (only if XDG_CONFIG_HOME explicitly set)
        if _has_explicit_xdg():
            return _xdg_config_home() / "suitewright" / "auth" / TOKEN_FILENAME

        # Mode 3: dev
        auth_dir = _auth_dir()
        if auth_dir is not None:
            return auth_dir / TOKEN_FILENAME

        # Mode 4: default
        return Path.home() / ".config" / "suitewright" / "auth" / TOKEN_FILENAME

    if kind == "client_secret":
        # Mode 1: env
        explicit = os.environ.get("SUITEWRIGHT_CLIENT_SECRET")
        if explicit:
            return Path(explicit).expanduser().resolve()
        root = _explicit_root()
        if root is not None:
            return root / "auth" / CLIENT_SECRET_FILENAME

        # Mode 2: xdg (only if XDG_CONFIG_HOME explicitly set)
        if _has_explicit_xdg():
            return _xdg_config_home() / "suitewright" / "auth" / CLIENT_SECRET_FILENAME

        # Mode 3: dev
        auth_dir = _auth_dir()
        if auth_dir is not None:
            return auth_dir / CLIENT_SECRET_FILENAME

        # Mode 4: default
        return Path.home() / ".config" / "suitewright" / "auth" / CLIENT_SECRET_FILENAME

    if kind == "cache_dir":
        # Mode 1: env
        explicit = os.environ.get("SUITEWRIGHT_CACHE_DIR")
        if explicit:
            return Path(explicit).expanduser().resolve()
        root = _explicit_root()
        if root is not None:
            return root / "cache"

        # XDG cache uses XDG_CACHE_HOME if set
        if "XDG_CACHE_HOME" in os.environ:
            return _xdg_cache_home() / "suitewright"

        # Dev mode: cache relative to dev root
        dev_root = _detect_dev_root()
        if dev_root is not None:
            return dev_root / "cache"

        # Default
        return Path.home() / ".cache" / "suitewright"

    if kind == "root":
        root = _explicit_root()
        if root is not None:
            return root

        if _has_explicit_xdg():
            return _xdg_config_home() / "suitewright"

        dev_root = _detect_dev_root()
        if dev_root is not None:
            return dev_root

        return Path.home() / ".config" / "suitewright"

    raise ValueError(f"unknown path kind: {kind!r}")


def exists(kind: Kind) -> bool:
    return resolve(kind).exists()


def describe() -> dict:
    """Describe the current auth resolution state.

    Returns a dict with mode ("env", "xdg", "dev", "default") and resolved paths.
    """
    if os.environ.get("SUITEWRIGHT_ROOT") or any(
        os.environ.get(var)
        for var in ("SUITEWRIGHT_TOKEN", "SUITEWRIGHT_CLIENT_SECRET", "SUITEWRIGHT_CACHE_DIR")
    ):
        mode = "env"
    elif _has_explicit_xdg():
        mode = "xdg"
    elif os.environ.get("SUITEWRIGHT_AUTH_DIR") or _detect_dev_root() is not None:
        mode = "dev"
    else:
        mode = "default"

    return {
        "mode": mode,
        "root": str(resolve("root")),
        "token": str(resolve("token")),
        "client_secret": str(resolve("client_secret")),
        "cache_dir": str(resolve("cache_dir")),
        "tokenExists": exists("token"),
        "clientSecretExists": exists("client_secret"),
    }
