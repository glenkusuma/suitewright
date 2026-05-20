# suitewright

**A portable Google Workspace CLI and workflow toolkit for humans and agents.**

`suitewright` is a Python command-line tool for working with Google Workspace from a local machine, automation script, or AI agent runtime. It is framework-neutral and built around a file-and-cache-first workflow that both humans and agents can inspect.

> Status: early standalone project (`v0.0.1-rc`). Commands and conventions may change.

## Why suitewright

Most Google Workspace tools are either thin API wrappers, one-off scripts, or integrations tied to a specific agent framework. `suitewright` is designed to be:

- **Portable** - works with `uv`, `pip`, a local `.venv`, or plain `python3`.
- **Agent-friendly** - useful to any agent that can run Python and read or write files.
- **Human-friendly** - usable as a normal CLI for everyday Workspace tasks.
- **Cache-first** - encourages safe local inspection before mutation. Currently implemented for Forms; Docs cache-first support is planned.
- **Multi-service** - covers Gmail, Calendar, Drive, Docs, Sheets, Contacts, and Forms.
- **Auth-aware** - treats OAuth setup and local credentials as first-class parts of the workflow.

## Installation

With `uv`:

```bash
uv tool install suitewright
```

With `pip`:

```bash
python3 -m pip install suitewright
```

From a checkout (development mode):

```bash
git clone https://github.com/glenkusuma/suitewright.git
cd suitewright
uv sync
uv run suitewright --help
```

## Agent Skill

Install the suitewright skill for your AI coding agent via [skills.sh](https://www.skills.sh/):

```bash
npx skills add glenkusuma/suitewright
```

## Authentication

`suitewright` uses local OAuth credentials on the machine where it runs.

Provide your Google OAuth client secret, complete browser-based consent once, and `suitewright` stores the resulting token locally. Run `suitewright auth check` at any point to see which path resolution mode is active and where files are being read from.

```bash
suitewright auth init --client-secret /path/to/client_secret.json
suitewright auth login
suitewright auth check
```

For headless or agent-driven flows, `auth login` accepts `--auth-url` and `--auth-code` as orthogonal flags so the consent step can be split across machines.

## Configuration paths

Auth file resolution follows a 4-mode precedence (highest wins):

| Priority | Mode | Source |
|----------|------|--------|
| 1 | `env` | `SUITEWRIGHT_TOKEN` / `SUITEWRIGHT_CLIENT_SECRET` env vars |
| 2 | `xdg` | `$XDG_CONFIG_HOME/suitewright/auth/` |
| 3 | `dev` | `SUITEWRIGHT_AUTH_DIR` (default `../suitewright-auth` relative to repo root) |
| 4 | `default` | `$HOME/.config/suitewright/auth/` |

Run `suitewright auth check --json` to see which mode is active. The output includes a `"mode"` field with one of: `"env"`, `"xdg"`, `"dev"`, `"default"`.

Cache resolution:

- `SUITEWRIGHT_CACHE_DIR` env var (if set)
- `$XDG_CACHE_HOME/suitewright/` (default `~/.cache/suitewright/`)

### Dev mode and `SUITEWRIGHT_AUTH_DIR`

In development, auth files are read from `SUITEWRIGHT_AUTH_DIR`. This defaults to `../suitewright-auth` relative to the detected repo root.

**Repo-root `auth/` is banned.** Auth credentials must never live inside the repository tree. The `_detect_dev_root()` function does not check for `auth/` at the repo root, and preflight scripts hard-fail if one exists. Use `SUITEWRIGHT_AUTH_DIR` to point to a directory outside the repo:

```bash
export SUITEWRIGHT_AUTH_DIR=/path/to/suitewright-auth
suitewright auth check --json  # confirms mode: "dev"
```

## Command surface

```text
suitewright auth          init | login | check | revoke | install-deps
suitewright gmail         search | get | send | reply | labels | modify | trash
suitewright calendar      list | create | delete
suitewright drive         search | get | upload | download | create-folder | share | delete
suitewright contacts      list
suitewright sheets        get | update | append
suitewright docs          get | show-structure | create | append | replace | update
                          request-template <kind>
                          replace-all | insert-table | insert-image | style-range
                          comments list | comments get | comments reply
                          table-get | table-update-cell | table-append-row
                          plan
suitewright forms         list | get | create | update
                          fetch | show-cache | validate | cache-update
                          query locate | query after | query delete-request
                          query get-item | query neighbors | query section | query indexer
```

Run any subcommand with `--help` for full flags.

### Examples

Inspect a Doc safely before editing:

```bash
suitewright docs show-structure DOC_ID --full-text
```

Validate a `batchUpdate` payload without mutating:

```bash
suitewright docs update DOC_ID --dry-run --requests-file edits.json
```

Cache-first Forms workflow:

```bash
suitewright forms fetch FORM_ID
suitewright forms query locate FORM_ID --title "Question 1"
suitewright forms cache-update FORM_ID /path/to/changes.json
```

Drive round-trip with safer-by-default delete:

```bash
suitewright drive upload report.pdf --parent FOLDER_ID
suitewright drive get FILE_ID
suitewright drive delete FILE_ID                # moves to trash
suitewright drive delete FILE_ID --permanent    # explicit irreversible delete
```

## Cache-first workflow philosophy

suitewright is designed around a cache-first pattern: fetch remote state once,
inspect and plan locally, then apply a guarded mutation and refresh.

```text
fetch live state
       ↓
write local cache artifact
       ↓
inspect / read / diff / patch locally
       ↓
compute safe edit plan
       ↓
apply guarded remote update
       ↓
refresh local cache
```

This pattern is currently implemented for **Forms** (`forms fetch` -> `forms query` -> `forms cache-update`).
Docs cache-first support is planned for a future release.

Local artifacts can be opened in an editor, read by an agent, committed to a branch, diffed, validated, patched, or fed into a repeatable script.

## Agent-friendly conventions

- JSON output is the default for inspection commands so it's easy to pipe into `jq` or feed into another tool.
- Mutation commands separate planning from applying. `docs update --dry-run` validates request shape; `docs plan` produces an inspectable plan artifact.
- Auth and config paths are explicit and discoverable via `auth check`.
- No hidden global state; everything resolves through `paths.resolve()` precedence.

## Development

```bash
git clone https://github.com/glenkusuma/suitewright.git
cd suitewright
uv sync
uv run suitewright --help
uv build
```

## Running Tests

Install dev dependencies and run the unit test suite (live tests are excluded by default):

```bash
uv sync
uv run pytest
```

Test layout:

```
tests/
├── unit/          # pure-function tests
├── integration/   # mocked-service full-path tests
├── scripts/       # helper script tests (scripts/docker.py)
└── live/          # real API tests (opt-in)
```

With coverage:

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

### Linting and type checking

```bash
uv run ruff check .
uv run mypy
uv run bandit -r src/suitewright
```

## Docker

A hardened Docker image is available for running suitewright in production or CI environments.

### Hardened runtime

Run with a read-only filesystem, all capabilities dropped, and explicit tmpfs mounts:

```bash
docker run --rm \
  --read-only \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --tmpfs /home/suitewright/.cache/suitewright:uid=1000,gid=1000,mode=700 \
  --tmpfs /home/suitewright/runtime:uid=1000,gid=1000,mode=700 \
  --tmpfs /tmp:uid=1000,gid=1000,mode=700 \
  -v "${SUITEWRIGHT_AUTH_DIR}":/home/suitewright/.config/suitewright/auth:ro \
  suitewright:local --help
```

### Auth mount

Auth files are mounted into the `auth/` subdir only - never over the entire config directory. This limits the container's read access to credentials only:

```bash
-v /path/to/suitewright-auth:/home/suitewright/.config/suitewright/auth:ro
```

The source path is controlled by `SUITEWRIGHT_AUTH_DIR`. The mount is read-only (`:ro`).

### docker-compose

The included `docker-compose.yml` configures both the runtime and test services with the same hardening. Auth is sourced from `SUITEWRIGHT_AUTH_DIR`:

```bash
SUITEWRIGHT_AUTH_DIR=/path/to/suitewright-auth docker compose up suitewright
```

### Dev workflow script

A contributor-friendly wrapper script handles building the test image and running tests in Docker:

```bash
uv run python scripts/docker.py build              # build test image
uv run python scripts/docker.py test               # run unit/integration tests
uv run python scripts/docker.py test --live        # run live API tests (with preflight checks)
uv run python scripts/docker.py test -k test_auth  # forward args to pytest
```

## License

Apache-2.0. See `LICENSE` and `NOTICE` for details.
