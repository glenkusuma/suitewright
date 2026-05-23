- ALWAYS USE PARALLEL TOOLS WHEN APPLICABLE.
- Run tests with `uv run pytest tests/` from the repo root.
- Never commit empherial session topic into codebase.
- Scratch notes, TODO tracking, and session artifacts go in `_local/` only.
- For agent usage guide, command reference, and OAuth setup: read `skills/suitewright-google-workspace/SKILL.md`.
- NEVER USE `—` or `–` in prose. Use `-`.
- NEVER USE `→` instead use `->`.

## Hard rules

### No credentials at repo root

Auth credentials are resolved via the `SUITEWRIGHT_AUTH_DIR` environment variable (default: `../suitewright-auth` relative to the detected dev root). The `_detect_dev_root()` function in `src/suitewright/_core/paths.py`.

- DO NOT READ OR COMMIT credential files (`google_token.json`, `google_client_secret.json`) to the repo. They are gitignored via explicit entries in `.gitignore`.
- Dev-mode auth files live outside the repo at the path specified by `SUITEWRIGHT_AUTH_DIR`.
- The 4-mode auth resolution precedence is: env vars - XDG - `SUITEWRIGHT_AUTH_DIR` - default (`~/.config/suitewright/auth/`).

## Repo orientation

Entry point: `suitewright` CLI (`src/suitewright/cli.py`).

Dev commands:
```bash
uv run suitewright --help     # run CLI from checkout
uv run pytest tests/          # run full test suite
uv build                      # build wheel + sdist
```

## Style guide

### General principles

- Each service module exposes a `register(subparsers)` function - follow this pattern when adding commands.
- Keep things in one function unless composable or reusable across modules.
- Do not extract single-use helpers preemptively. Inline the logic at the call site.
- No comments unless the WHY is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug.
- Do not explain WHAT the code does - well-named identifiers already do that.

### Control flow

- Prefer early returns over nested conditionals.
- Avoid `else` after a `return` or `raise`.

### Output conventions

- JSON output on stdout for all inspection and mutation commands.
- Errors and status messages go to stderr via `raise SystemExit(...)` or `print(..., file=sys.stderr)`.
- Never mix JSON and plain text on stdout in the same command path.

### CLI patterns

- Positional args for required IDs (e.g. `form_id`, `doc_id`).
- `--flag` for optional modifiers.
- Mutually exclusive groups via `add_mutually_exclusive_group()` where applicable (see `forms/query.py`).
- Sub-subcommands via nested `add_subparsers()` (see `forms/__init__.py` for the `forms query` pattern).

## Testing

- Mock `build_service` at the module level where it is imported, not at `suitewright._core.service.build_service`.
  Example: `patch("suitewright.gmail.build_service", return_value=svc)`
- Use `MagicMock()` for service objects; chain `.method().execute.return_value = ...` to set responses.
- Do not hit real Google APIs in tests.
- Integration tests live in `tests/integration/test_integration_cli.py` and cover the full dispatch path.
- Argparse contract tests live in `tests/unit/test_cli_argparse.py`.

### Test directory layout

```
tests/
├── conftest.py            # shared fixtures (available to all subdirs)
├── unit/                  # pure-function tests (no I/O, no mocked services)
├── integration/           # full dispatch path with mocked Google API services
├── scripts/               # helper script tests (scripts/docker.py, etc.)
└── live/                  # real API tests (opt-in via --run-live)
```

## Mutation safety

- Confirm with the user before any write operation (send email, create/delete events, modify Docs/Sheets/Forms).
- Inspect before mutate: use `docs query structure` before Docs edits, `forms validate` before Forms updates.
- `drive delete` moves to trash by default - `--permanent` is explicit and irreversible.
- `docs mutate raw --dry-run` validates request shape without mutating.

## Pre-commit checklist

**Never commit without running through all of these checks.** A commit that skips this checklist may leak session artifacts, secrets, or stale documentation into the public repo.

### 1. Ephemeral session content in tracked files

```bash
# Hardcoded dates that look like session artifacts (today's date, run timestamps)
rg "\d{4}-\d{2}-\d{2}" tests/ src/ --glob "*.py" | grep -v "2025-01-15\|# example\|ISO 8601\|dateTime\|modifiedTime\|createdAt"

# Specific run IDs, Drive folder IDs, or resource IDs (format: 1[a-zA-Z0-9_-]{28,})
rg "1[a-zA-Z0-9_-]{28,}" tests/ src/ skills/ README.md AGENTS.md .env.example

# References to deleted scripts
rg "bootstrap\.sh|check_leaks\.sh" tests/ src/ AGENTS.md README.md .env.example
```

### 2. Secrets and credentials

```bash
# .env must be gitignored - never committed
git check-ignore -v .env
# expected: .gitignore:NN:.env  .env

# auth/ directory must be gitignored
git check-ignore -v auth/google_token.json auth/google_client_secret.json

# No token or client secret values in tracked files
rg "client_secret|ya29\.|\"token\"\s*:" tests/ src/ --glob "*.py" | grep -v "path\|file\|resolve\|args\."
```

### 3. _local/ drift check

`_local/` is gitignored and never committed, but stale guides mislead future agents.

### 4. Documentation consistency

```bash
# README command surface matches actual CLI
uv run suitewright --help

# AGENTS.md skill reference is valid
test -f skills/suitewright-google-workspace/SKILL.md && echo OK

# .env.example has no real values (all optional fields blank or default)
grep -E "^[A-Z_]+=.+" .env.example | grep -v "primary\|suitewright-live-test\|\./auth/"
# expected: no output (no filled-in secrets)

# Version consistency: pyproject.toml, __init__.py, and SKILL.md must match
grep 'version = ' pyproject.toml | head -1
grep '__version__' src/suitewright/__init__.py
grep 'version:' skills/suitewright-google-workspace/SKILL.md
# expected: all three show the same version string
```

### 5. Test suite

```bash
# Mock suite must pass
uv run pytest tests/ -q --ignore=tests/live
# expected: all passed (count may vary as tests are added)

# No unknown mark warnings
uv run pytest tests/ -q --ignore=tests/live 2>&1 | grep -i "warning\|unknown mark"
# expected: no output
```

### 6. Git status sanity

```bash
# Review what will be committed
git status
git diff --cached

# Confirm no unintended files are staged
# These must NEVER appear in git status as staged:
#   .env, auth/, cache/, _local/, *.session.json, *.session.md, CLAUDE.md, .claude/
git status | grep -E "\.env$|auth/|cache/|_local/|\.session\.|CLAUDE\.md|\.claude/"
# expected: no output
```

Live tests hit real Google APIs and require `--run-live`. Rules for agents:

- **Never run live tests without redirecting output to a log file.** Always use:
  ```bash
  uv run pytest tests/live/ -m <tier> --run-live > _local/tests/live/.runs/<name>.log 2>&1; echo "exit: $?"
  ```
- **Never stream or tee live test output into the conversation context** - it is too large. Use redirect only.
- **To inspect results**, use `tail`, `Read`, or `rg` (ripgrep) on the log file:
  ```bash
  tail -30 _local/tests/live/.runs/<name>.log
  rg "FAILED|ERROR|passed|failed" _local/tests/live/.runs/<name>.log
  ```
- **To check for leaks after a run:**
  ```bash
  uv run python tests/live/scripts/check_leaks.py
  ```
- **Bootstrap (first-time setup):**
  ```bash
  uv run python tests/live/scripts/bootstrap.py
  ```
