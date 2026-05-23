"""Query engine for cached Google Docs — local inspection commands.

Provides structural inspection and text extraction over the locally cached
document JSON. Zero API calls — all operations read from the cache.

Reuses helpers from _core.render (paragraph_text, show_structure_block,
compact_preview) and extends them with additional metadata for the query CLI.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator

from suitewright._core.cache import CacheStore
from suitewright._core.output import emit_json, emit_text, error_exit
from suitewright._core.render import compact_preview, show_structure_block

_cache = CacheStore("docs")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def extract_text(paragraph: dict) -> str:
    """Extract concatenated text from a paragraph's elements.

    Extends _core.render.paragraph_text by explicitly skipping
    inlineObjectElement entries (images between text runs).
    Only processes textRun entries.
    """
    parts: list[str] = []
    for el in paragraph.get("elements", []):
        # Explicitly skip inlineObjectElement and any other non-text elements
        if "inlineObjectElement" in el:
            continue
        text_run = el.get("textRun")
        if text_run:
            content = text_run.get("content")
            if content:
                parts.append(content)
    return "".join(parts)


def iter_structural_elements(doc: dict) -> Iterator[dict]:
    """Yield structural elements from body.content, skipping sectionBreak.

    All real documents start with a sectionBreak at index 0. This iterator
    filters those out so callers only see paragraph and table elements.
    """
    for element in doc.get("body", {}).get("content", []):
        if "sectionBreak" in element:
            continue
        yield element


# ---------------------------------------------------------------------------
# Block metadata builder (extends show_structure_block)
# ---------------------------------------------------------------------------


def _block_metadata(element: dict, index: int, *, full_text: bool) -> dict | None:
    """Build metadata for a structural element block.

    Starts from _core.render.show_structure_block and extends with:
    - list info (listId, nestingLevel) for bullet paragraphs
    - positionedImages for paragraphs referencing positioned objects
    """
    # Get base block from shared render helper
    block = show_structure_block(element, index, full_text=full_text)
    if block is None:
        return None

    # Extend paragraph blocks with additional metadata
    if "paragraph" in element:
        paragraph = element["paragraph"]

        # Override text extraction to use our extract_text (skips inlineObjectElement)
        text = extract_text(paragraph).rstrip("\n")
        if full_text:
            block["text"] = text
        else:
            block["preview"] = compact_preview(text)

        # List membership
        bullet = paragraph.get("bullet")
        if bullet:
            block["list"] = {
                "listId": bullet["listId"],
                "nestingLevel": bullet.get("nestingLevel", 0),
            }

        # Positioned image references
        positioned_ids = paragraph.get("positionedObjectIds")
        if positioned_ids:
            block["positionedImages"] = positioned_ids

    return block


# ---------------------------------------------------------------------------
# CLI command: structure
# ---------------------------------------------------------------------------


def cmd_structure(args) -> None:
    """Show structural outline of the cached document.

    Outputs blocks with kind, preview/text, indices, list info, and
    positioned image references. With --full-text, includes namedRanges.
    """
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)
    full_text = getattr(args, "full_text", False)

    blocks: list[dict] = []
    for idx, element in enumerate(iter_structural_elements(doc)):
        block = _block_metadata(element, idx, full_text=full_text)
        if block is not None:
            blocks.append(block)

    output: dict = {
        "documentId": doc.get("documentId", args.doc_id),
        "title": doc.get("title", ""),
        "blockCount": len(blocks),
        "blocks": blocks,
    }

    # Include namedRanges summary when --full-text is provided
    if full_text:
        named_ranges = doc.get("namedRanges", {})
        if named_ranges:
            output["namedRanges"] = [
                {"name": name, "rangeCount": len(ranges.get("namedRanges", []))}
                for name, ranges in named_ranges.items()
            ]

    compact = getattr(args, "compact", False)
    emit_json(output, compact=compact)


# ---------------------------------------------------------------------------
# Heading helpers
# ---------------------------------------------------------------------------

_HEADING_STYLES = {
    "HEADING_1": 1,
    "HEADING_2": 2,
    "HEADING_3": 3,
    "HEADING_4": 4,
    "HEADING_5": 5,
    "HEADING_6": 6,
}


def get_heading_level(element: dict) -> int | None:
    """Return heading level (1-6) if element is a heading paragraph, else None."""
    paragraph = element.get("paragraph")
    if not paragraph:
        return None
    style = paragraph.get("paragraphStyle", {}).get("namedStyleType", "")
    return _HEADING_STYLES.get(style)


# ---------------------------------------------------------------------------
# CLI command: get
# ---------------------------------------------------------------------------


def cmd_get(args) -> None:
    """Get document body as plain text (textRun.content only).

    Concatenates all textRun.content values from paragraphs in the cached
    document. Skips inlineObjectElement and other non-text elements.
    """
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)

    parts: list[str] = []
    for element in iter_structural_elements(doc):
        if "paragraph" in element:
            text = extract_text(element["paragraph"])
            if text:
                parts.append(text)
        elif "table" in element:
            # Extract text from table cells
            table = element["table"]
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    for cell_el in cell.get("content", []):
                        if "paragraph" in cell_el:
                            text = extract_text(cell_el["paragraph"])
                            if text:
                                parts.append(text)

    emit_text("".join(parts))


# ---------------------------------------------------------------------------
# CLI command: list-headings
# ---------------------------------------------------------------------------


def cmd_list_headings(args) -> None:
    """List all headings (HEADING_1 through HEADING_6) with their metadata.

    Includes empty headings (paragraphs styled as HEADING_N with no text
    content), marking them with "empty": true.
    """
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)

    headings: list[dict] = []
    para_index = 0
    for element in iter_structural_elements(doc):
        if "paragraph" not in element:
            # Tables still count for structural iteration but not paragraph index
            continue

        level = get_heading_level(element)
        if level is not None:
            text = extract_text(element["paragraph"]).rstrip("\n")
            is_empty = text.strip() == ""
            heading_entry: dict = {
                "text": text if not is_empty else "",
                "level": level,
                "startIndex": element.get("startIndex", 0),
                "endIndex": element.get("endIndex", 0),
                "paragraphIndex": para_index,
                "empty": is_empty,
            }
            headings.append(heading_entry)

        para_index += 1

    compact = getattr(args, "compact", False)
    emit_json(headings, compact=compact)


# ---------------------------------------------------------------------------
# CLI command: find-heading
# ---------------------------------------------------------------------------


def cmd_find_heading(args) -> None:
    """Find a heading by exact text match (default) or --fuzzy substring match.

    Reports matchCount when there are duplicates. Returns the first match.
    If not found, exits with error listing available non-empty headings.
    """
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)
    fuzzy = getattr(args, "fuzzy", False)
    search_text = args.text

    matches: list[dict] = []
    para_index = 0
    for element in iter_structural_elements(doc):
        if "paragraph" not in element:
            continue

        level = get_heading_level(element)
        if level is not None:
            text = extract_text(element["paragraph"]).rstrip("\n")
            matched = False
            if fuzzy:
                matched = search_text.lower() in text.lower()
            else:
                matched = text.strip() == search_text

            if matched:
                matches.append(
                    {
                        "text": text,
                        "level": level,
                        "startIndex": element.get("startIndex", 0),
                        "endIndex": element.get("endIndex", 0),
                        "paragraphIndex": para_index,
                    }
                )

        para_index += 1

    if not matches:
        # Collect non-empty headings as suggestions
        suggestions: list[str] = []
        for element in iter_structural_elements(doc):
            if "paragraph" not in element:
                continue
            level = get_heading_level(element)
            if level is not None:
                text = extract_text(element["paragraph"]).rstrip("\n")
                if text.strip():
                    suggestions.append(text.strip())

        error_exit(
            "error",
            "HEADING_NOT_FOUND",
            f"No heading found matching '{search_text}'.",
            documentId=args.doc_id,
            suggestions=suggestions,
        )

    result = matches[0].copy()
    if len(matches) > 1:
        result["matchCount"] = len(matches)

    compact = getattr(args, "compact", False)
    emit_json(result, compact=compact)


# ---------------------------------------------------------------------------
# CLI command: section
# ---------------------------------------------------------------------------


def cmd_section(args) -> None:
    """Extract elements between two headings.

    Returns all structural elements from the matched heading to the next
    heading of equal or higher level (lower number). Empty headings act
    as boundaries.
    """
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)
    fuzzy = getattr(args, "fuzzy", False)
    search_text = args.heading

    # Find the target heading
    elements = list(iter_structural_elements(doc))
    target_idx: int | None = None
    target_level: int | None = None

    para_index = 0
    for i, element in enumerate(elements):
        if "paragraph" not in element:
            continue

        level = get_heading_level(element)
        if level is not None:
            text = extract_text(element["paragraph"]).rstrip("\n")
            matched = False
            if fuzzy:
                matched = search_text.lower() in text.lower()
            else:
                matched = text.strip() == search_text

            if matched and target_idx is None:
                target_idx = i
                target_level = level

        para_index += 1

    if target_idx is None:
        # Collect non-empty headings as suggestions
        suggestions: list[str] = []
        for element in elements:
            if "paragraph" not in element:
                continue
            level = get_heading_level(element)
            if level is not None:
                text = extract_text(element["paragraph"]).rstrip("\n")
                if text.strip():
                    suggestions.append(text.strip())

        error_exit(
            "error",
            "HEADING_NOT_FOUND",
            f"No heading found matching '{search_text}'.",
            documentId=args.doc_id,
            suggestions=suggestions,
        )

    # Collect elements from target heading to next heading of same or higher level
    section_elements: list[dict] = []
    # target_level is guaranteed non-None here (set alongside target_idx)
    _target_level: int = target_level if target_level is not None else 1

    for i in range(target_idx, len(elements)):
        element = elements[i]

        # Check if this is a boundary heading (skip the target itself)
        if i > target_idx:
            level = get_heading_level(element)
            if level is not None and level <= _target_level:
                break
            # Empty headings also act as boundaries
            if level is not None:
                text = extract_text(element["paragraph"]).rstrip("\n")
                if text.strip() == "":
                    break

        # Build element metadata
        block = _block_metadata(element, i, full_text=True)
        if block is not None:
            section_elements.append(block)

    compact = getattr(args, "compact", False)
    emit_json(section_elements, compact=compact)


# ---------------------------------------------------------------------------
# CLI command: find-text
# ---------------------------------------------------------------------------


def cmd_find_text(args) -> None:
    """Regex search on paragraph text (textRun only).

    Returns matches with context, startIndex/endIndex, and paragraph index.
    Interprets --pattern as a Python regular expression.
    """
    import re

    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    # Validate regex pattern
    try:
        pattern = re.compile(args.pattern)
    except re.error as exc:
        error_exit(
            "error",
            "INVALID_REGEX",
            f"Invalid regex pattern: {exc}",
            pattern=args.pattern,
        )

    doc = _cache.load(args.doc_id)

    matches: list[dict] = []
    para_index = 0
    for element in iter_structural_elements(doc):
        if "paragraph" not in element:
            continue

        text = extract_text(element["paragraph"])
        if pattern.search(text):
            matches.append(
                {
                    "text": text.rstrip("\n"),
                    "startIndex": element.get("startIndex", 0),
                    "endIndex": element.get("endIndex", 0),
                    "paragraphIndex": para_index,
                }
            )

        para_index += 1

    compact = getattr(args, "compact", False)
    emit_json(matches, compact=compact)


# ---------------------------------------------------------------------------
# CLI command: get-range
# ---------------------------------------------------------------------------


def cmd_get_range(args) -> None:
    """Filter structural elements by startIndex/endIndex overlap with a given range.

    Returns elements whose [startIndex, endIndex) overlaps with [--start, --end).
    """
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)
    range_start = args.start
    range_end = args.end

    result_elements: list[dict] = []
    text_parts: list[str] = []

    idx = 0
    for element in iter_structural_elements(doc):
        el_start = element.get("startIndex", 0)
        el_end = element.get("endIndex", 0)

        # Check overlap: element overlaps range if el_start < range_end and el_end > range_start
        if el_start < range_end and el_end > range_start:
            block = _block_metadata(element, idx, full_text=True)
            if block is not None:
                result_elements.append(block)

            # Extract text for paragraphs
            if "paragraph" in element:
                text = extract_text(element["paragraph"])
                if text:
                    text_parts.append(text)
            elif "table" in element:
                table = element["table"]
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        for cell_el in cell.get("content", []):
                            if "paragraph" in cell_el:
                                text = extract_text(cell_el["paragraph"])
                                if text:
                                    text_parts.append(text)

        idx += 1

    output = {
        "documentId": doc.get("documentId", args.doc_id),
        "rangeStart": range_start,
        "rangeEnd": range_end,
        "text": "".join(text_parts),
        "elements": result_elements,
    }

    compact = getattr(args, "compact", False)
    emit_json(output, compact=compact)


# ---------------------------------------------------------------------------
# CLI command: word-count
# ---------------------------------------------------------------------------


def cmd_word_count(args) -> None:
    """Word count: total + per-section breakdown.

    Invariant: total == sum of all section word counts.
    If --heading is provided, returns word count for that section only.
    """
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)
    heading_filter = getattr(args, "heading", None)

    # Build sections: list of (heading_text, level, word_count)
    # A "section" is text between one heading and the next
    sections: list[dict] = []
    current_heading = "(before first heading)"
    current_level = 0
    current_words = 0

    for element in iter_structural_elements(doc):
        if "paragraph" not in element:
            # Tables: count words in table cells
            if "table" in element:
                table = element["table"]
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        for cell_el in cell.get("content", []):
                            if "paragraph" in cell_el:
                                text = extract_text(cell_el["paragraph"])
                                words = text.split()
                                current_words += len(words)
            continue

        level = get_heading_level(element)
        if level is not None:
            # Save current section
            sections.append(
                {
                    "heading": current_heading,
                    "level": current_level,
                    "wordCount": current_words,
                }
            )
            # Start new section
            text = extract_text(element["paragraph"]).rstrip("\n")
            current_heading = text if text.strip() else "(empty heading)"
            current_level = level
            current_words = 0
        else:
            # Regular paragraph — count words
            text = extract_text(element["paragraph"])
            words = text.split()
            current_words += len(words)

    # Don't forget the last section
    sections.append(
        {
            "heading": current_heading,
            "level": current_level,
            "wordCount": current_words,
        }
    )

    total = sum(s["wordCount"] for s in sections)

    # If --heading filter is provided, return only that section
    if heading_filter:
        for section in sections:
            if section["heading"].strip() == heading_filter.strip():
                output = {
                    "heading": section["heading"],
                    "level": section["level"],
                    "wordCount": section["wordCount"],
                }
                compact = getattr(args, "compact", False)
                emit_json(output, compact=compact)
                return

        error_exit(
            "error",
            "HEADING_NOT_FOUND",
            f"No section found for heading '{heading_filter}'.",
            documentId=args.doc_id,
        )

    output = {
        "documentId": doc.get("documentId", args.doc_id),
        "total": total,
        "sections": sections,
    }

    compact = getattr(args, "compact", False)
    emit_json(output, compact=compact)


# ---------------------------------------------------------------------------
# CLI command: find-citations
# ---------------------------------------------------------------------------


def cmd_find_citations(args) -> None:
    """Find parenthetical citation patterns in the document.

    Detects patterns like (Author, 2024), (Author et al., 2023),
    (Author & Other, 2022), etc.
    """
    import re

    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)

    # Citation regex: parenthetical with a year (19xx or 20xx)
    citation_pattern = re.compile(r"\([^)]*(?:19|20)\d{2}[^)]*\)")

    citations: list[dict] = []
    para_index = 0
    for element in iter_structural_elements(doc):
        if "paragraph" not in element:
            continue

        text = extract_text(element["paragraph"])
        for match in citation_pattern.finditer(text):
            citations.append(
                {
                    "text": match.group(),
                    "startIndex": element.get("startIndex", 0),
                    "endIndex": element.get("endIndex", 0),
                    "paragraphIndex": para_index,
                    "matchStart": match.start(),
                    "matchEnd": match.end(),
                }
            )

        para_index += 1

    compact = getattr(args, "compact", False)
    emit_json(citations, compact=compact)


# ---------------------------------------------------------------------------
# CLI command: check-headings
# ---------------------------------------------------------------------------


def cmd_check_headings(args) -> None:
    """Check heading integrity: duplicates, skipped levels, empty headings.

    Reports:
    - duplicateHeadings: headings with the same text (grouped)
    - skippedLevels: places where heading level jumps (e.g., H1 → H3)
    - emptyHeadings: headings with no text content
    """
    if not _cache.exists(args.doc_id):
        error_exit(
            "error",
            "CACHE_MISSING",
            "Cache not found. Run `docs cache fetch` first.",
            documentId=args.doc_id,
            expectedPath=str(_cache.path(args.doc_id)),
        )

    doc = _cache.load(args.doc_id)

    # Collect all headings
    headings: list[dict] = []
    para_index = 0
    for element in iter_structural_elements(doc):
        if "paragraph" not in element:
            continue

        level = get_heading_level(element)
        if level is not None:
            text = extract_text(element["paragraph"]).rstrip("\n")
            headings.append(
                {
                    "text": text,
                    "level": level,
                    "startIndex": element.get("startIndex", 0),
                    "endIndex": element.get("endIndex", 0),
                    "paragraphIndex": para_index,
                }
            )

        para_index += 1

    # Detect duplicates (by text, excluding empty)
    text_counts: dict[str, list[dict]] = {}
    for h in headings:
        if h["text"].strip():
            key = h["text"].strip()
            if key not in text_counts:
                text_counts[key] = []
            text_counts[key].append(h)

    duplicate_headings: list[dict] = []
    for text, entries in text_counts.items():
        if len(entries) > 1:
            duplicate_headings.append(
                {
                    "text": text,
                    "count": len(entries),
                    "locations": [
                        {"startIndex": e["startIndex"], "paragraphIndex": e["paragraphIndex"]}
                        for e in entries
                    ],
                }
            )

    # Detect skipped levels (e.g., H1 → H3 without H2)
    skipped_levels: list[dict] = []
    for i in range(1, len(headings)):
        prev_level = headings[i - 1]["level"]
        curr_level = headings[i]["level"]
        # A skip occurs when the current level is more than 1 deeper than previous
        if curr_level > prev_level + 1:
            skipped_levels.append(
                {
                    "from": {
                        "text": headings[i - 1]["text"],
                        "level": prev_level,
                        "paragraphIndex": headings[i - 1]["paragraphIndex"],
                    },
                    "to": {
                        "text": headings[i]["text"],
                        "level": curr_level,
                        "paragraphIndex": headings[i]["paragraphIndex"],
                    },
                    "skipped": list(range(prev_level + 1, curr_level)),
                }
            )

    # Detect empty headings
    empty_headings: list[dict] = []
    for h in headings:
        if h["text"].strip() == "":
            empty_headings.append(
                {
                    "level": h["level"],
                    "startIndex": h["startIndex"],
                    "endIndex": h["endIndex"],
                    "paragraphIndex": h["paragraphIndex"],
                }
            )

    output = {
        "documentId": doc.get("documentId", args.doc_id),
        "totalHeadings": len(headings),
        "duplicateHeadings": duplicate_headings,
        "skippedLevels": skipped_levels,
        "emptyHeadings": empty_headings,
    }

    compact = getattr(args, "compact", False)
    emit_json(output, compact=compact)


# ---------------------------------------------------------------------------
# Subcommand registration
# ---------------------------------------------------------------------------


def register(sub: argparse._SubParsersAction) -> None:
    """Register all 10 query subcommands."""
    # structure
    p = sub.add_parser("structure", help="Show structural outline (blocks, tables)")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument(
        "--full-text",
        action="store_true",
        help="Include full text content and namedRanges",
    )
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_structure)

    # get
    p = sub.add_parser("get", help="Get document body as plain text from cache")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.set_defaults(func=cmd_get)

    # list-headings
    p = sub.add_parser("list-headings", help="List all headings with levels")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_list_headings)

    # find-heading
    p = sub.add_parser("find-heading", help="Locate a heading by text")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--text", required=True, help="Heading text to search for")
    p.add_argument(
        "--fuzzy",
        action="store_true",
        help="Use case-insensitive substring matching",
    )
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_find_heading)

    # section
    p = sub.add_parser("section", help="Extract content between headings")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--heading", required=True, help="Heading text to find section for")
    p.add_argument(
        "--fuzzy",
        action="store_true",
        help="Use case-insensitive substring matching",
    )
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_section)

    # find-text
    p = sub.add_parser("find-text", help="Regex search in paragraphs")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--pattern", required=True, help="Python regex pattern to search for")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_find_text)

    # get-range
    p = sub.add_parser("get-range", help="Extract text by index range")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--start", type=int, required=True, help="Start index (inclusive)")
    p.add_argument("--end", type=int, required=True, help="End index (exclusive)")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_get_range)

    # word-count
    p = sub.add_parser("word-count", help="Word count (total + per-section)")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--heading", help="Return word count for this section only")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_word_count)

    # find-citations
    p = sub.add_parser("find-citations", help="Detect academic citation patterns")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_find_citations)

    # check-headings
    p = sub.add_parser("check-headings", help="Report duplicate/skipped heading levels")
    p.add_argument("doc_id", help="Google Docs document ID")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=cmd_check_headings)
