"""Cache lifecycle commands for Google Docs (fetch, show, validate, update).

Implements the docs cache-first workflow: fetch a document into local JSON cache,
show cache metadata, validate cache freshness, and execute guarded batchUpdate
with automatic cache refresh.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from suitewright._core.cache import CacheStore
from suitewright._core.output import emit_json, error_exit, warn
from suitewright._core.retry import execute_with_backoff
from suitewright._core.service import build_service

_cache = CacheStore("docs")


def fetch_doc(doc_id: str) -> dict:
    """Fetch a Google Doc via documents.get with backoff retry."""
    service = build_service("docs", "v1")
    return execute_with_backoff(lambda: service.documents().get(documentId=doc_id).execute())


def cmd_fetch(args) -> None:
    """Fetch a Google Doc into local JSON cache."""
    doc = fetch_doc(args.doc_id)
    path = _cache.write(args.doc_id, doc)

    revision_id = doc.get("revisionId")
    status: dict = {
        "status": "cached",
        "documentId": doc["documentId"],
        "title": doc["title"],
        "cachePath": str(path),
    }
    if revision_id:
        status["revisionId"] = revision_id
    else:
        warn(
            "revisionId absent (no edit access). Staleness guards use cacheHash only.",
            documentId=args.doc_id,
        )

    compact = getattr(args, "compact", False)
    emit_json(status, compact=compact)


def cmd_show(args) -> None:
    """Print cache file path and metadata JSON."""
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    path = _cache.path(args.doc_id)
    cached = _cache.load(args.doc_id)
    cache_hash = _cache.hash(args.doc_id)

    metadata = {
        "documentId": cached.get("documentId", args.doc_id),
        "title": cached.get("title", ""),
        "revisionId": cached.get("revisionId"),
        "cacheHash": cache_hash,
        "cachePath": str(path),
    }

    compact = getattr(args, "compact", False)
    emit_json(metadata, compact=compact)


def cmd_validate(args) -> None:
    """Validate cache freshness (cacheHash + revisionId checks)."""
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    cached = _cache.load(args.doc_id)
    computed_hash = _cache.hash(args.doc_id)
    revision_id = cached.get("revisionId")

    # Check expected-revision if provided
    if args.expected_revision and revision_id != args.expected_revision:
        error_exit(
            "stale",
            "REVISION_MISMATCH",
            "Cached revision does not match expected.",
            cachedRevision=revision_id,
            expectedRevision=args.expected_revision,
        )

    # Check expected-hash if provided
    if args.expected_hash and computed_hash != args.expected_hash:
        error_exit(
            "stale",
            "HASH_MISMATCH",
            "Cache hash does not match expected.",
            cachedHash=computed_hash,
            expectedHash=args.expected_hash,
        )

    result = {
        "status": "ok",
        "documentId": cached.get("documentId", args.doc_id),
        "cachePath": str(_cache.path(args.doc_id)),
        "cacheHash": computed_hash,
        "revisionId": revision_id,
    }

    compact = getattr(args, "compact", False)
    emit_json(result, compact=compact)


def _build_batch_update_body(requests: list[dict], revision_id: str | None) -> dict:
    """Build the batchUpdate request body, including writeControl when possible.

    When revision_id is available, includes writeControl.requiredRevisionId
    so the API enforces optimistic concurrency (rejects if doc changed).
    """
    body: dict = {"requests": requests}
    if revision_id:
        body["writeControl"] = {"requiredRevisionId": revision_id}
    return body


def cmd_update(args) -> None:
    """Execute guarded batchUpdate: validate staleness, apply requests, refresh cache.

    Workflow:
    1. Load requests from file
    2. Validate cache staleness (revisionId comparison if available,
       else cacheHash-only with warning)
    3. If --dry-run, print requests and exit
    4. Execute batchUpdate with writeControl.requiredRevisionId when available
    5. Re-fetch document and overwrite cache
    """
    # 1. Load and validate requests file
    requests_path = Path(args.requests_file)
    if not requests_path.exists():
        error_exit(
            "error",
            "FILE_NOT_FOUND",
            f"Requests file not found: {args.requests_file}",
            path=str(requests_path),
        )

    try:
        requests_data = json.loads(requests_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        error_exit(
            "error",
            "INVALID_JSON",
            f"Requests file contains invalid JSON: {exc}",
            path=str(requests_path),
        )

    if not isinstance(requests_data, list):
        error_exit(
            "error",
            "INVALID_FORMAT",
            "Requests file must contain a JSON array of request objects.",
            path=str(requests_path),
        )

    # 2. Validate cache exists
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    cached = _cache.load(args.doc_id)
    revision_id = cached.get("revisionId")

    # 3. Staleness check
    if revision_id:
        # Full staleness check: compare cached revisionId with live
        service = build_service("docs", "v1")
        live_doc = execute_with_backoff(
            lambda: service.documents().get(documentId=args.doc_id, fields="revisionId").execute()
        )
        live_revision = live_doc.get("revisionId")
        if revision_id != live_revision:
            error_exit(
                "stale",
                "REVISION_MISMATCH",
                "Document changed since last fetch. Run `docs cache fetch` first.",
                cachedRevision=revision_id,
                liveRevision=live_revision,
            )
    else:
        # No revisionId — cacheHash-only mode with warning
        warn(
            "No revisionId in cache. Cannot verify remote staleness. "
            "Proceeding with cacheHash-only validation.",
            documentId=args.doc_id,
        )

    # 4. Dry-run: print what would be sent and exit
    compact = getattr(args, "compact", False)
    if args.dry_run:
        dry_run_result = {
            "status": "dry-run",
            "documentId": args.doc_id,
            "requestCount": len(requests_data),
            "requests": requests_data,
        }
        if revision_id:
            dry_run_result["writeControl"] = {"requiredRevisionId": revision_id}
        emit_json(dry_run_result, compact=compact)
        return

    # 5. Execute batchUpdate with writeControl when possible
    body = _build_batch_update_body(requests_data, revision_id)
    service = build_service("docs", "v1")
    result = execute_with_backoff(
        lambda: service.documents().batchUpdate(documentId=args.doc_id, body=body).execute()
    )

    # 6. Re-fetch and overwrite cache
    fresh_doc = execute_with_backoff(
        lambda: service.documents().get(documentId=args.doc_id).execute()
    )
    cache_path = _cache.write(args.doc_id, fresh_doc)

    # 7. Emit success status
    status: dict = {
        "status": "updated",
        "documentId": args.doc_id,
        "cachePath": str(cache_path),
    }
    new_revision = fresh_doc.get("revisionId")
    if new_revision:
        status["revisionId"] = new_revision
    status["batchUpdateResponse"] = result

    emit_json(status, compact=compact)


def register(sub: argparse._SubParsersAction) -> None:
    """Register fetch, show, validate, and update subcommands."""
    # fetch
    p = sub.add_parser("fetch", help="Fetch live doc into local JSON cache")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_fetch)

    # show
    p = sub.add_parser("show", help="Print cache file path + metadata")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_show)

    # validate
    p = sub.add_parser("validate", help="Check cache freshness (revisionId + hash)")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument(
        "--expected-revision",
        default="",
        help="Expected revisionId to compare against cached value",
    )
    p.add_argument(
        "--expected-hash",
        default="",
        help="Expected SHA-256 hash to compare against cache file",
    )
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_validate)

    # update
    p = sub.add_parser("update", help="Guarded batchUpdate + auto-refresh cache")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("requests_file", help="Path to JSON file containing batchUpdate requests")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print requests without executing",
    )
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_update)
