"""State lifecycle helper for cache-first Google Forms workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from suitewright._core.retry import execute_with_backoff
from suitewright._core.service import build_service
from suitewright.forms.cache import cache_path, ensure_cache_root


def cache_payload(form_id: str) -> dict:
    path = cache_path(form_id)
    if not path.exists():
        raise SystemExit(f"Cache not found: {path}. Run fetch first.")
    return json.loads(path.read_text())


def cache_hash(form_id: str) -> str:
    path = cache_path(form_id)
    if not path.exists():
        raise SystemExit(f"Cache not found: {path}. Run fetch first.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_form(form_id: str) -> dict:
    service = build_service("forms", "v1")
    return execute_with_backoff(lambda: service.forms().get(formId=form_id).execute())


def write_cache(form_id: str, payload: dict) -> Path:
    ensure_cache_root()
    path = cache_path(form_id)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def _minimal_print(payload: dict, *, verbose: bool) -> None:
    if verbose:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            json.dumps(
                {
                    k: v
                    for k, v in payload.items()
                    if k in {"status", "index", "itemId", "questionId", "count"}
                },
                ensure_ascii=False,
            )
        )


def cmd_fetch(args):
    payload = fetch_form(args.form_id)
    write_cache(args.form_id, payload)
    _minimal_print({"status": "cached"}, verbose=args.verbose)


def cmd_show_cache(args):
    path = cache_path(args.form_id)
    if not path.exists():
        raise SystemExit(f"Cache not found: {path}. Run fetch first.")
    print(path)


def cmd_validate(args):
    payload = cache_payload(args.form_id)
    result = {
        "formId": args.form_id,
        "cachePath": str(cache_path(args.form_id)),
        "cacheHash": cache_hash(args.form_id),
        "revisionId": payload.get("revisionId", ""),
    }

    if args.expected_revision and payload.get("revisionId") != args.expected_revision:
        raise SystemExit(
            json.dumps(
                (
                    {
                        "status": "stale",
                        **result,
                        "expectedRevision": args.expected_revision,
                    }
                    if args.verbose
                    else {"status": "stale"}
                ),
                indent=2,
                ensure_ascii=False,
            )
        )

    items = payload.get("items", [])
    if args.expect_item_id:
        for idx, item in enumerate(items):
            if item.get("itemId") == args.expect_item_id:
                result.update({"status": "ok", "foundItemId": args.expect_item_id, "index": idx})
                _minimal_print(result, verbose=args.verbose)
                return
        raise SystemExit(
            json.dumps(
                (
                    {
                        "status": "missing-target",
                        **result,
                        "expectedItemId": args.expect_item_id,
                    }
                    if args.verbose
                    else {"status": "missing-target"}
                ),
                indent=2,
                ensure_ascii=False,
            )
        )

    if args.expect_title:
        for idx, item in enumerate(items):
            if item.get("title") == args.expect_title:
                result.update({"status": "ok", "foundTitle": args.expect_title, "index": idx})
                _minimal_print(result, verbose=args.verbose)
                return
        raise SystemExit(
            json.dumps(
                (
                    {
                        "status": "missing-target",
                        **result,
                        "expectedTitle": args.expect_title,
                    }
                    if args.verbose
                    else {"status": "missing-target"}
                ),
                indent=2,
                ensure_ascii=False,
            )
        )

    result["status"] = "ok"
    _minimal_print(result, verbose=args.verbose)


def cmd_update(args):
    current = cache_payload(args.form_id)
    current_hash = cache_hash(args.form_id)

    if args.expected_revision and current.get("revisionId") != args.expected_revision:
        raise SystemExit(
            json.dumps(
                (
                    {
                        "status": "stale",
                        "formId": args.form_id,
                        "cachePath": str(cache_path(args.form_id)),
                        "cacheHash": current_hash,
                        "revisionId": current.get("revisionId", ""),
                        "expectedRevision": args.expected_revision,
                    }
                    if args.verbose
                    else {"status": "stale"}
                ),
                indent=2,
                ensure_ascii=False,
            )
        )

    if args.expected_hash and current_hash != args.expected_hash:
        raise SystemExit(
            json.dumps(
                (
                    {
                        "status": "stale",
                        "formId": args.form_id,
                        "cachePath": str(cache_path(args.form_id)),
                        "cacheHash": current_hash,
                        "expectedHash": args.expected_hash,
                    }
                    if args.verbose
                    else {"status": "stale"}
                ),
                indent=2,
                ensure_ascii=False,
            )
        )

    requests = json.loads(Path(args.requests_file).read_text())
    service = build_service("forms", "v1")
    payload = {"requests": requests}
    if args.include_form_in_response:
        payload["includeFormInResponse"] = True
    result = execute_with_backoff(
        lambda: service.forms().batchUpdate(formId=args.form_id, body=payload).execute()
    )

    refreshed = fetch_form(args.form_id)
    write_cache(args.form_id, refreshed)

    output = {
        "status": "updated",
        "formId": args.form_id,
        "cachePath": str(cache_path(args.form_id)),
        "result": result,
    }

    replies = result.get("replies", [])
    if replies:
        create = replies[0].get("createItem") if isinstance(replies[0], dict) else None
        if create:
            output["itemId"] = create.get("itemId", "")
            qids = create.get("questionId", [])
            if qids:
                output["questionId"] = qids[0]
    _minimal_print(output, verbose=args.verbose)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("fetch", help="Fetch live form into local cache")
    p.add_argument("form_id")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("show-cache", help="Print the cache path for a form")
    p.add_argument("form_id")
    p.set_defaults(func=cmd_show_cache)

    p = sub.add_parser("validate", help="Validate cache assumptions before mutation")
    p.add_argument("form_id")
    p.add_argument("--expected-revision", default="")
    p.add_argument("--expect-item-id", default="")
    p.add_argument("--expect-title", default="")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser(
        "cache-update",
        help="Apply a guarded batchUpdate then refresh the local cache",
    )
    p.add_argument("form_id")
    p.add_argument("requests_file", help="Path to JSON list of batchUpdate requests")
    p.add_argument("--expected-revision", default="")
    p.add_argument("--expected-hash", default="")
    p.add_argument("--include-form-in-response", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_update)
