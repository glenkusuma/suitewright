"""Check version consistency across pyproject.toml, __init__.py, and SKILL.md.

Exits non-zero if any version source disagrees. Intended for CI and pre-commit.

Usage:
    uv run python scripts/check_version.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCES = {
    "pyproject.toml": (
        REPO_ROOT / "pyproject.toml",
        re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE),
    ),
    "__init__.py": (
        REPO_ROOT / "src" / "suitewright" / "__init__.py",
        re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE),
    ),
    "SKILL.md": (
        REPO_ROOT / "skills" / "suitewright-google-workspace" / "SKILL.md",
        re.compile(r'^\s*version:\s*"([^"]+)"', re.MULTILINE),
    ),
}


def main() -> int:
    versions: dict[str, str] = {}
    errors: list[str] = []

    for name, (path, pattern) in SOURCES.items():
        if not path.exists():
            errors.append(f"{name}: file not found at {path}")
            continue
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        if not match:
            errors.append(f"{name}: version pattern not found in {path}")
            continue
        versions[name] = match.group(1)

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    unique = set(versions.values())
    if len(unique) == 1:
        version = unique.pop()
        print(f"OK: all sources agree on version {version}")
        for name, ver in versions.items():
            print(f"  {name}: {ver}")
        return 0

    print("MISMATCH: version sources disagree", file=sys.stderr)
    for name, ver in versions.items():
        print(f"  {name}: {ver}", file=sys.stderr)
    print("\nUpdate all three to the same version before releasing.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
