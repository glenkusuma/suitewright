# Docs request-template styling references

## Purpose

Keep `docs request-template style-range` minimal while preserving a reusable
place for richer Docs text-style examples.

## Core rule

The `fields` mask must match the exact `textStyle` properties being set.

## Currently supported

The `docs request-template style-range` command generates a `bold`-only starter
template. The `docs style-range` command currently accepts `--bold` to apply
bold formatting to a text range.

```json
[
  {
    "updateTextStyle": {
      "range": {
        "startIndex": 1,
        "endIndex": 10
      },
      "textStyle": {
        "bold": true
      },
      "fields": "bold"
    }
  }
]
```

## Future extension examples

These are valid Docs API `textStyle` properties that may be added in future versions:

- `italic`
- `underline`
- `foregroundColor`
- `backgroundColor`
- `link`

Example richer mask:

```json
"fields": "italic,foregroundColor"
```

Example richer payload:

```json
[
  {
    "updateTextStyle": {
      "range": {
        "startIndex": 1,
        "endIndex": 10
      },
      "textStyle": {
        "italic": true,
        "foregroundColor": {
          "color": {
            "rgbColor": {
              "red": 0.2,
              "green": 0.4,
              "blue": 0.8
            }
          }
        }
      },
      "fields": "italic,foregroundColor"
    }
  }
]
```

The `fields` mask must list exactly the keys present in `textStyle` — no more,
no less. Omitting a key from `fields` means that property will not be changed
even if it appears in `textStyle`.
