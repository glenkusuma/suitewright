# Google Docs Fixtures

Local JSON fixtures from the Google Docs API for live testing of the docs-cache-workflow commands. Each fixture is a full `documents.get()` response stored by name.

## Fixtures

### Request for Proposal

- **File:** `request-for-proposal.json`
- **Paragraphs:** 106
- **Tables:** 1
- **Images:** 7 inline, 1 positioned
- **Lists:** 35
- **Headers/Footers:** yes / yes
- **Heading levels:** heading_1, heading_2
- **Selection rationale:** Richest structure - tables, images, lists, headers/footers, 2 heading levels

### Brochure

- **File:** `brochure.json`
- **Paragraphs:** 17
- **Tables:** 0
- **Images:** 0 inline, 5 positioned
- **Lists:** 0
- **Headers/Footers:** yes / yes
- **Heading levels:** heading_1, heading_2, heading_3
- **Selection rationale:** Positioned images, 3 heading levels, minimal text

### Statement of Work

- **File:** `statement-of-work.json`
- **Paragraphs:** 59
- **Tables:** 4
- **Images:** 2 inline, 0 positioned
- **Lists:** 0
- **Headers/Footers:** yes / no
- **Heading levels:** heading_1, heading_2
- **Selection rationale:** Multiple tables, inline images, lists

### Recipe

- **File:** `recipe.json`
- **Paragraphs:** 20
- **Tables:** 0
- **Images:** 1 inline, 0 positioned
- **Lists:** 10
- **Headers/Footers:** no / no
- **Heading levels:** heading_1
- **Selection rationale:** Simple structure - single heading level, minimal images, lists

## Coverage Matrix

| Capability | Request for Proposal | Brochure | Statement of Work | Recipe |
|---|---|---|---|---|
| `paragraphs` | yes | yes | yes | yes |
| `tables` | yes | - | yes | - |
| `inline_images` | yes | - | yes | yes |
| `positioned_images` | yes | yes | - | - |
| `lists` | yes | - | yes | yes |
| `headers` | yes | yes | yes | - |
| `footers` | yes | yes | - | - |
| `heading_1` | yes | yes | yes | yes |
| `heading_2` | yes | yes | yes | - |
| `heading_3` | - | yes | - | - |

## Usage

```python
from tests.live.fixtures.docs import load_fixture, load_fixture_by_name

# Load first fixture that has tables
doc = load_fixture("tables")

# Load by name
doc = load_fixture_by_name("Request for Proposal")
```

## Exports

DOCX and PDF exports of each fixture are in `exports/` for gap analysis between JSON structure and rendered output.
