#!/usr/bin/env python3
"""Resolve GitHub Action version tags to commit SHAs.

Reads .github/workflows/*.yml files, resolves `org/action@vX` references
to their full commit SHAs via the GitHub API, rewrites workflow files
in-place with `<SHA> # vX.Y.Z` format, and updates .github/actions-lock.md.

Usage:
    uv run python scripts/resolve-action-shas.py          # resolve and rewrite
    uv run python scripts/resolve-action-shas.py --check  # validate only (no writes)

Requires GITHUB_TOKEN env var for API access (avoids rate limits).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
LOCK_FILE = REPO_ROOT / ".github" / "actions-lock.md"

# Matches: uses: org/action@ref  or  uses: org/action/sub@ref
# Handles both `- uses:` (list item) and `uses:` (map value) forms
# Captures: (prefix), (action path), (ref), optional (# comment)
USES_RE = re.compile(
    r"^(\s*-?\s*uses:\s*)"  # prefix: indentation, optional dash, 'uses:'
    r"([a-zA-Z0-9\-_.]+/[a-zA-Z0-9\-_.]+(?:/[a-zA-Z0-9\-_.]+)*)"  # action path
    r"@([^\s#]+)"  # @ref (tag, branch, or SHA)
    r"(\s*#\s*.*)?"  # optional existing comment
    r"$",
    re.MULTILINE,
)

# 40-char hex SHA pattern
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def get_github_token() -> str | None:
    """Get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def github_api_get(url: str, token: str | None = None) -> dict:
    """Make a GET request to the GitHub API."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, headers=headers)  # noqa: S310
    try:
        with urlopen(req, timeout=30) as resp:  # noqa: S310
            return json.loads(resp.read().decode())
    except HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Not found: {url}") from e
        raise


def resolve_tag_to_sha(action: str, tag: str, token: str | None = None) -> tuple[str, str]:
    """Resolve an action version tag to its commit SHA.

    Returns (sha, resolved_version) where resolved_version is the full tag name
    (e.g., 'v4.2.2' even if input was 'v4').
    """
    # If already a SHA, just return it
    if SHA_RE.match(tag):
        return tag, tag

    # Try exact tag first via git ls-remote (works without token for public repos)
    sha = _resolve_via_git_ls_remote(action, tag)
    if sha:
        return sha, tag

    # Try GitHub API: get the tag reference
    # First try exact match
    sha, version = _resolve_via_api(action, tag, token)
    if sha:
        return sha, version

    raise ValueError(f"Could not resolve {action}@{tag}")


def _resolve_via_git_ls_remote(action: str, tag: str) -> str | None:
    """Try to resolve a tag using git ls-remote."""
    url = f"https://github.com/{action}.git"
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", url, f"refs/tags/{tag}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Format: <sha>\trefs/tags/<tag>
            # For annotated tags, we need the dereferenced commit
            lines = result.stdout.strip().split("\n")
            # Prefer ^{} (dereferenced) if available
            for line in lines:
                if line.endswith("^{}"):
                    return line.split("\t")[0]
            # Otherwise use the first match
            return lines[0].split("\t")[0]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _resolve_via_api(action: str, tag: str, token: str | None) -> tuple[str | None, str]:
    """Resolve a tag via the GitHub API.

    Handles both exact tags and major version tags (e.g., v4 -> v4.2.2).
    """
    # Try to get the exact git ref
    try:
        data = github_api_get(
            f"https://api.github.com/repos/{action}/git/ref/tags/{tag}",
            token,
        )
        sha = _resolve_ref_object(action, data["object"], token)
        return sha, tag
    except (ValueError, KeyError):
        pass

    # If tag is a major version (e.g., v4), find the latest matching release
    if re.match(r"^v\d+$", tag):
        return _resolve_major_version(action, tag, token)

    return None, tag


def _resolve_ref_object(action: str, obj: dict, token: str | None) -> str:
    """Resolve a git ref object to a commit SHA (handles annotated tags)."""
    if obj["type"] == "commit":
        return obj["sha"]
    elif obj["type"] == "tag":
        # Annotated tag - need to dereference
        tag_data = github_api_get(obj["url"], token)
        return tag_data["object"]["sha"]
    return obj["sha"]


def _resolve_major_version(
    action: str, major_tag: str, token: str | None
) -> tuple[str | None, str]:
    """Resolve a major version tag (e.g., v4) to the latest patch release SHA."""
    major_num = major_tag.lstrip("v")

    # List tags matching this major version
    try:
        # Use git ls-remote to list all tags
        url = f"https://github.com/{action}.git"
        result = subprocess.run(
            ["git", "ls-remote", "--tags", url, f"refs/tags/v{major_num}*"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            # Parse version tags and find the highest
            versions: list[tuple[str, str]] = []
            for line in lines:
                parts = line.split("\t")
                if len(parts) == 2:
                    ref = parts[1].replace("refs/tags/", "").rstrip("^{}")
                    if re.match(rf"^v{major_num}\.\d+\.\d+$", ref):
                        versions.append((ref, parts[0]))

            if versions:
                # Sort by version number
                versions.sort(
                    key=lambda x: [int(n) for n in x[0].lstrip("v").split(".")],
                    reverse=True,
                )
                best_tag = versions[0][0]
                # Resolve the specific tag SHA
                sha = _resolve_via_git_ls_remote(action, best_tag)
                if sha:
                    return sha, best_tag
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: try the major tag directly via ls-remote
    sha = _resolve_via_git_ls_remote(action, major_tag)
    if sha:
        return sha, major_tag

    return None, major_tag


def find_workflow_files() -> list[Path]:
    """Find all workflow YAML files."""
    if not WORKFLOWS_DIR.exists():
        return []
    return sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml"))


def parse_action_refs(content: str) -> list[dict]:
    """Parse all action references from workflow file content.

    Returns list of dicts with keys: action, ref, line_start, line_end, full_match
    """
    refs = []
    for match in USES_RE.finditer(content):
        refs.append(
            {
                "prefix": match.group(1),
                "action": match.group(2),
                "ref": match.group(3),
                "comment": match.group(4) or "",
                "full_match": match.group(0),
                "start": match.start(),
                "end": match.end(),
            }
        )
    return refs


def rewrite_workflow_content(
    content: str, resolutions: dict[tuple[str, str], tuple[str, str]]
) -> str:
    """Rewrite workflow content with resolved SHAs.

    resolutions: {(action, original_ref): (sha, version)}
    """

    def replace_match(match: re.Match) -> str:
        prefix = match.group(1)
        action = match.group(2)
        ref = match.group(3)

        key = (action, ref)
        if key in resolutions:
            sha, version = resolutions[key]
            return f"{prefix}{action}@{sha} # {version}"
        # If already a SHA with comment, leave as-is
        return match.group(0)

    return USES_RE.sub(replace_match, content)


def generate_lock_content(
    resolutions: dict[tuple[str, str], tuple[str, str]],
) -> str:
    """Generate the actions-lock.md content."""
    lines = [
        "# GitHub Actions Lock File",
        "",
        "This file records the SHA-pinned versions of all GitHub Actions used in workflows.",
        "Generated by `scripts/resolve-action-shas.py`.",
        "",
        "| Action | Version | SHA |",
        "|--------|---------|-----|",
    ]

    # Sort by action name for deterministic output
    sorted_entries = sorted(resolutions.items(), key=lambda x: (x[0][0], x[0][1]))
    seen = set()
    for (action, _original_ref), (sha, version) in sorted_entries:
        entry_key = (action, sha)
        if entry_key in seen:
            continue
        seen.add(entry_key)
        lines.append(f"| `{action}` | {version} | `{sha}` |")

    lines.append("")
    return "\n".join(lines)


def check_lock_matches(
    resolutions: dict[tuple[str, str], tuple[str, str]],
) -> list[str]:
    """Check that the lock file matches current workflow state.

    Returns list of error messages (empty = all good).
    """
    errors = []

    if not LOCK_FILE.exists():
        errors.append(f"Lock file not found: {LOCK_FILE}")
        return errors

    lock_content = LOCK_FILE.read_text()
    expected_content = generate_lock_content(resolutions)

    if lock_content != expected_content:
        errors.append(
            "Lock file content does not match resolved actions. "
            "Run `scripts/resolve-action-shas.py` to update."
        )

    # Also check that workflow files use SHAs (not tags)
    for wf_file in find_workflow_files():
        content = wf_file.read_text()
        for ref_info in parse_action_refs(content):
            ref = ref_info["ref"]
            action = ref_info["action"]
            # Skip local actions (e.g., ./.github/actions/...)
            if action.startswith("."):
                continue
            if not SHA_RE.match(ref):
                errors.append(f"{wf_file.name}: {action}@{ref} is not SHA-pinned")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve GitHub Action version tags to commit SHAs"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that lock file matches workflow files without modifying them",
    )
    args = parser.parse_args()

    token = get_github_token()
    if not token:
        print("Warning: GITHUB_TOKEN not set. API requests may be rate-limited.", file=sys.stderr)

    workflow_files = find_workflow_files()
    if not workflow_files:
        print("No workflow files found in .github/workflows/", file=sys.stderr)
        return 1

    # Collect all action references across all workflow files
    all_refs: dict[tuple[str, str], None] = {}  # (action, ref) -> None (ordered set)
    for wf_file in workflow_files:
        content = wf_file.read_text()
        for ref_info in parse_action_refs(content):
            action = ref_info["action"]
            ref = ref_info["ref"]
            # Skip if already SHA-pinned (in check mode, we still validate)
            if not args.check and SHA_RE.match(ref):
                # Already resolved - extract version from comment if present
                comment = ref_info["comment"].strip().lstrip("#").strip()
                if comment:
                    all_refs[(action, ref)] = None
                continue
            all_refs[(action, ref)] = None

    # Resolve all unique action@ref pairs
    resolutions: dict[tuple[str, str], tuple[str, str]] = {}
    for action, ref in all_refs:
        if SHA_RE.match(ref):
            # Already a SHA - keep it, use comment as version
            resolutions[(action, ref)] = (ref, ref[:8])
            continue
        try:
            sha, version = resolve_tag_to_sha(action, ref, token)
            resolutions[(action, ref)] = (sha, version)
            print(f"  {action}@{ref} -> {sha[:12]} # {version}")
        except ValueError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            return 1

    if args.check:
        # In check mode, also parse already-pinned refs from workflow files
        for wf_file in workflow_files:
            content = wf_file.read_text()
            for ref_info in parse_action_refs(content):
                action = ref_info["action"]
                ref = ref_info["ref"]
                comment = ref_info["comment"].strip().lstrip("#").strip()
                if SHA_RE.match(ref) and comment:
                    resolutions[(action, ref)] = (ref, comment)

        errors = check_lock_matches(resolutions)
        if errors:
            print("Lock file validation failed:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        print("Lock file is up to date.")
        return 0

    # Rewrite workflow files in-place
    for wf_file in workflow_files:
        content = wf_file.read_text()
        new_content = rewrite_workflow_content(content, resolutions)
        if new_content != content:
            wf_file.write_text(new_content)
            print(f"  Updated: {wf_file.name}")

    # Update lock file
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_content = generate_lock_content(resolutions)
    LOCK_FILE.write_text(lock_content)
    print(f"  Updated: {LOCK_FILE.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
