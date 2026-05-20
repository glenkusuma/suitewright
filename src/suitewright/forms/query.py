"""Structured query helpers over cached Google Forms state.

Includes an `indexer` action for cache-first title-pattern indexing
(e.g. question labels like `A1.`, `B2.`, `Q0.`) so agents can locate
question-like items without resorting to ad-hoc Python snippets.
"""

from __future__ import annotations

import argparse
import json
import re

from suitewright.forms.cache import cache_path

DEFAULT_LABEL_PATTERN = r"^[A-Z]\d+\."


def load_form(form_id: str) -> dict:
    path = cache_path(form_id)
    if not path.exists():
        raise SystemExit(f"Cache not found: {path}")
    return json.loads(path.read_text())


def top_level_items(form: dict) -> list[dict]:
    return form.get("items", [])


def compact_item(item: dict, index: int) -> dict:
    out = {
        "index": index,
        "itemId": item.get("itemId", ""),
        "title": item.get("title", ""),
    }
    if item.get("description"):
        out["description"] = item.get("description")
    if "textItem" in item:
        out["kind"] = "textItem"
    elif "imageItem" in item:
        out["kind"] = "imageItem"
    elif "questionGroupItem" in item:
        out["kind"] = "questionGroupItem"
    elif "questionItem" in item:
        out["kind"] = "questionItem"
        q = item.get("questionItem", {}).get("question", {})
        out["questionId"] = q.get("questionId", "")
        if q.get("required") is not None:
            out["required"] = q.get("required", False)
        if "textQuestion" in q:
            out["questionType"] = "text"
            if q.get("textQuestion", {}).get("paragraph"):
                out["paragraph"] = True
        if "choiceQuestion" in q:
            out["questionType"] = q.get("choiceQuestion", {}).get("type", "")
            out["options"] = q.get("choiceQuestion", {}).get("options", [])
    return out


def find_index_by_item_id(form: dict, item_id: str) -> int:
    for idx, item in enumerate(top_level_items(form)):
        if item.get("itemId") == item_id:
            return idx
    raise SystemExit(f"Item ID not found: {item_id}")


def find_index_by_title(form: dict, title: str) -> int:
    for idx, item in enumerate(top_level_items(form)):
        if item.get("title") == title:
            return idx
    raise SystemExit(f"Title not found: {title}")


def _resolve_idx(form: dict, args) -> int:
    if args.item_id:
        return find_index_by_item_id(form, args.item_id)
    return find_index_by_title(form, args.title)


def cmd_locate(args):
    form = load_form(args.form_id)
    print(json.dumps({"index": _resolve_idx(form, args)}, indent=2))


def cmd_after(args):
    form = load_form(args.form_id)
    print(json.dumps({"afterIndex": _resolve_idx(form, args) + 1}, indent=2))


def cmd_delete_request(args):
    form = load_form(args.form_id)
    idx = _resolve_idx(form, args)
    print(json.dumps([{"deleteItem": {"location": {"index": idx}}}], indent=2, ensure_ascii=False))


def cmd_get_item(args):
    form = load_form(args.form_id)
    items = top_level_items(form)
    idx = _resolve_idx(form, args)
    print(json.dumps(compact_item(items[idx], idx), indent=2, ensure_ascii=False))


def cmd_neighbors(args):
    form = load_form(args.form_id)
    items = top_level_items(form)
    idx = _resolve_idx(form, args)
    start = max(0, idx - args.before)
    end = min(len(items), idx + args.after + 1)
    payload = [compact_item(items[i], i) for i in range(start, end)]
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_section(args):
    form = load_form(args.form_id)
    items = top_level_items(form)
    idx = _resolve_idx(form, args)

    start = idx
    while start > 0 and not items[start].get("title", "").startswith("Bagian "):
        start -= 1
    end = idx + 1
    while end < len(items) and not items[end].get("title", "").startswith("Bagian "):
        end += 1

    payload = [compact_item(items[i], i) for i in range(start, end)]
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_indexer(args):
    try:
        regex = re.compile(args.pattern)
    except re.error as exc:
        raise SystemExit(f"Invalid regex pattern: {exc}") from exc

    form = load_form(args.form_id)
    items = top_level_items(form)
    matches = []
    for idx, item in enumerate(items):
        title = item.get("title", "")
        m = regex.search(title)
        if not m:
            continue

        if args.group is not None:
            try:
                label = m.group(args.group)
            except IndexError as exc:
                raise SystemExit(f"Group {args.group} not present in pattern match: {exc}") from exc
        else:
            label = m.group(0)

        compact = compact_item(item, idx)
        matches.append(
            {
                "index": idx,
                "itemId": compact.get("itemId", ""),
                "title": title,
                "label": label,
                "kind": compact.get("kind", ""),
            }
        )

    print(
        json.dumps(
            {
                "formId": args.form_id,
                "pattern": args.pattern,
                "matchCount": len(matches),
                "matches": matches,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _add_target(p: argparse.ArgumentParser) -> None:
    p.add_argument("form_id")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--item-id")
    group.add_argument("--title")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("locate", help="Locate an item by ID or title")
    _add_target(p)
    p.set_defaults(func=cmd_locate)

    p = sub.add_parser("after", help="Compute the insertion index after a target")
    _add_target(p)
    p.set_defaults(func=cmd_after)

    p = sub.add_parser("delete-request", help="Emit a deleteItem request payload")
    _add_target(p)
    p.set_defaults(func=cmd_delete_request)

    p = sub.add_parser("get-item", help="Fetch one item from the cached form")
    _add_target(p)
    p.set_defaults(func=cmd_get_item)

    p = sub.add_parser("neighbors", help="Show items around a target")
    _add_target(p)
    p.add_argument("--before", type=int, default=1)
    p.add_argument("--after", type=int, default=1)
    p.set_defaults(func=cmd_neighbors)

    p = sub.add_parser("section", help="Show items within a 'Bagian *' section")
    _add_target(p)
    p.set_defaults(func=cmd_section)

    p = sub.add_parser(
        "indexer",
        help="Index items whose titles match a label-style regex pattern",
    )
    p.add_argument("form_id")
    p.add_argument(
        "--pattern",
        default=DEFAULT_LABEL_PATTERN,
        help=f"Regex applied to item titles. Default: {DEFAULT_LABEL_PATTERN}",
    )
    p.add_argument(
        "--group",
        type=int,
        default=None,
        help="Optional regex group index to extract as `label`",
    )
    p.set_defaults(func=cmd_indexer)
