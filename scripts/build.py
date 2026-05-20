#!/usr/bin/env python3
"""Build suitewright and regenerate checksums/SHA256SUMS.

Usage:
    uv run python scripts/build.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
CHECKSUMS_DIR = REPO_ROOT / "checksums"
CHECKSUMS_FILE = CHECKSUMS_DIR / "SHA256SUMS"


def sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    """Build and regenerate checksums."""
    # Clean old dist
    if DIST_DIR.exists():
        for f in DIST_DIR.iterdir():
            f.unlink()

    # Build
    result = subprocess.run(
        ["uv", "build", "--sdist", "--wheel"],
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print("build: Error: uv build failed", file=sys.stderr)
        sys.exit(result.returncode)

    # Generate checksums
    CHECKSUMS_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = sorted(DIST_DIR.glob("*"))
    if not artifacts:
        print("build: Error: no artifacts in dist/", file=sys.stderr)
        sys.exit(1)

    lines = []
    for artifact in artifacts:
        digest = sha256_file(artifact)
        lines.append(f"{digest}  {artifact.name}")
        print(f"  {digest}  {artifact.name}", file=sys.stderr)

    CHECKSUMS_FILE.write_text("\n".join(lines) + "\n")
    print(f"build: checksums written to {CHECKSUMS_FILE.relative_to(REPO_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
