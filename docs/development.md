# Development

## Dev setup

```bash
git clone https://github.com/glenkusuma/suitewright.git
cd suitewright
uv sync
uv run suitewright --help
uv build
```

## Running tests

Install dev dependencies and run the unit test suite (live tests are excluded by default):

```bash
uv sync
uv run pytest
```

### Test layout

```
tests/
├── unit/          # pure-function tests (no I/O, no mocked services)
├── integration/   # mocked-service full-path tests
├── scripts/       # helper script tests (scripts/docker.py)
└── live/          # real API tests (opt-in)
```

### Coverage

```bash
uv run pytest --cov=suitewright
```

### Live tests

Live tests hit real Google APIs and require valid credentials. They are opt-in:

```bash
uv run pytest -m live --run-live
```

Markers available:

| Marker | Description |
|--------|-------------|
| `live` | Requires a real Google account; opt-in via `--run-live` |
| `smoke` | Read-only sanity checks against live APIs |
| `mutate` | Creates or modifies real resources (sandboxed) |
| `destructive` | Sends, deletes, or otherwise acts irreversibly (sandboxed) |

## Linting and type checking

```bash
uv run ruff check .
uv run mypy
uv run bandit -r src/suitewright
```

## Pre-commit checklist

See `AGENTS.md` for the full pre-commit checklist that must be run before every commit.
