"""Docs structural-element rendering helpers.

Used by docs.basic for show-structure, by docs.semantic for replace-all
changedBlocks previews, and by docs.tables for cell text extraction.
"""

from __future__ import annotations


def paragraph_text(paragraph: dict) -> str:
    parts = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun", {})
        content = text_run.get("content")
        if content:
            parts.append(content)
    return "".join(parts)


def table_text(table: dict) -> str:
    rows = []
    for row in table.get("tableRows", []):
        cells = []
        for cell in row.get("tableCells", []):
            cells.append(structural_elements_text(cell.get("content", []), joiner=" ").strip())
        rows.append("\t".join(cells).rstrip())
    return "\n".join(rows)


def structural_elements_text(elements: list, joiner: str = "\n") -> str:
    blocks = []
    for element in elements:
        if "paragraph" in element:
            text = paragraph_text(element["paragraph"])
            if text:
                blocks.append(text)
        elif "table" in element:
            t = table_text(element["table"])
            if t:
                blocks.append(t)
        elif "tableOfContents" in element:
            toc = structural_elements_text(
                element["tableOfContents"].get("content", []), joiner=joiner
            )
            if toc:
                blocks.append(toc)
    return joiner.join(blocks)


def compact_preview(text: str, limit: int = 100) -> str:
    text = " ".join(text.split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def show_structure_block(element: dict, index: int, *, full_text: bool) -> dict | None:
    start_index = element.get("startIndex", 0)
    block = {
        "index": index,
        "startIndex": start_index,
        "endIndex": element.get("endIndex", start_index),
    }

    if "paragraph" in element:
        block["kind"] = "paragraph"
        text = paragraph_text(element["paragraph"]).rstrip("\n")
        if full_text:
            block["text"] = text
        else:
            block["preview"] = compact_preview(text)
        return block

    if "tableOfContents" in element:
        block["kind"] = "tableOfContents"
        text = structural_elements_text(element["tableOfContents"].get("content", []), joiner="\n")
        if full_text:
            block["text"] = text
        else:
            block["preview"] = compact_preview(text)
        return block

    if "table" in element:
        table = element["table"]
        rows = table.get("tableRows", [])
        block["kind"] = "table"
        block["rows"] = len(rows)
        block["cols"] = max((len(row.get("tableCells", [])) for row in rows), default=0)
        if full_text:
            block["text"] = table_text(table)
        return block

    return None


def document_end_index(doc: dict) -> int:
    content = doc.get("body", {}).get("content", [])
    if not content:
        return 1
    return max(1, content[-1].get("endIndex", 1))
