# tests/live — Live CLI tests against a real Google account

These tests exercise the suitewright CLI end-to-end against the Google Workspace APIs.
They are **opt-in** and **never** run as part of the default `uv run pytest` flow.

## Safety model

Three nested tiers gate progressively riskier work:

| Marker | What runs | Effect |
|---|---|---|
| `smoke` | read-only commands | reads only |
| `mutate` | create / update / append on Docs, Sheets, Forms, Drive | writes inside a per-run sandbox folder + Gmail label |
| `destructive` | sends email, deletes events, trashes Drive items | only acts on resources the test created |

Every test under `tests/live/` carries `@pytest.mark.live` plus exactly one tier marker.
A session-scoped fixture (`sandbox`) creates a uniquely-named Drive folder and Gmail
label at startup, tracks every created resource, and cleans them up on teardown.

## Prerequisites

- Python 3.11+ and `uv` on PATH.
- A Google account with access to the APIs suitewright targets (Gmail, Calendar,
  Drive, Docs, Sheets, Contacts, Forms).
- An OAuth desktop client secret JSON downloaded from
  https://console.cloud.google.com/apis/credentials.

## First-time setup

```bash
# 1. Create your env file
cp .env.example .env

# 2. Edit .env — the only required value is the path to your client secret:
#    SUITEWRIGHT_LIVE_TEST_CLIENT_SECRET=../suitewright-auth/google_client_secret.json

# 3. Run the bootstrap script (idempotent)
uv run python tests/live/scripts/bootstrap.py
```

The script will:
1. Init suitewright with your client secret (`suitewright auth init`).
2. Open a browser for OAuth consent (`suitewright auth login`).
3. Verify the token is valid (`suitewright auth check`).
4. Create a persistent `suitewright-tests` Drive folder and print its ID — paste it into `.env` as `SUITEWRIGHT_LIVE_TEST_ROOT_FOLDER_ID`.

Re-run bootstrap after setting the root folder ID to verify it.

Headless / agent re-auth (no browser):

```bash
HEADLESS=1 uv run python tests/live/scripts/bootstrap.py
# Visit the printed URL, complete consent, copy the redirected URL, then:
uv run suitewright auth login --auth-code 'PASTED_URL_OR_CODE'
```

## Sandbox root folder

By default, sandbox run folders are created in your Drive root. Set `SUITEWRIGHT_LIVE_TEST_ROOT_FOLDER_ID` in `.env` to nest all per-run folders inside a persistent parent folder (`suitewright-tests`). The bootstrap script creates this folder automatically on first run.

This keeps your Drive root clean and makes manual sweeps easy — all test artifacts are under one folder.

## Checking for leaks

After any run, verify no resources leaked:

```bash
uv run python tests/live/scripts/check_leaks.py
```

Exits 0 if clean. Exits 1 and prints details if any of the following are found:
- Drive resources matching the sandbox prefix still exist
- `leaked.json` files in `_local/tests/live/.runs/`
- `cleanup.json` entries with `ok: false`

## Running the suite

Live tests are **excluded from the default test run**. Running `uv run pytest` only
executes the unit/mock suite — live tests are never collected.

To run live tests, you must **explicitly target** the `tests/live/` directory:

```bash
# Smoke (under 60s, read-only)
uv run pytest tests/live/ -m smoke --run-live -v

# Mutate (creates resources in sandbox)
uv run pytest tests/live/ -m mutate --run-live -v

# Destructive (sends, deletes — sandbox-scoped)
uv run pytest tests/live/ -m destructive --run-live -v

# Full sweep (all tiers + e2e, runs sequentially: smoke → mutate → destructive → e2e)
uv run pytest tests/live/ --run-live -v
```

### Sequential execution

Live tests **cannot run in parallel**. Even if `pytest-xdist` is installed, the
live conftest forces `-n 0` (single-process) when `tests/live/` is targeted.

When running the full sweep, tests are automatically ordered by risk tier:
1. `smoke` (read-only) runs first
2. `mutate` (creates/modifies) runs second
3. `destructive` (sends/deletes) runs third
4. `e2e` (multi-step flows) runs last

This ensures lower-risk tests validate connectivity before riskier operations begin.

Without `--run-live`, every test under `tests/live/` is skipped. The default
`uv run pytest` runs only the mock suite (no live APIs touched).

## Environment variables

See `.env.example` for the full list with defaults. Highlights:

- `SUITEWRIGHT_LIVE_TEST_CLIENT_SECRET` (required) — path to OAuth client secret.
- `SUITEWRIGHT_LIVE_TEST_EMAIL` — sender + recipient for self-addressed test emails.
  Defaults to the authenticated account (derived from sent mail).
- `SUITEWRIGHT_LIVE_TEST_CALENDAR_ID` — defaults to `primary`. Use a dedicated
  test calendar if you do not want events on your primary calendar.
- `SUITEWRIGHT_LIVE_TEST_PREFIX` — default `suitewright-live-test`. All sandbox
  resources are named with this prefix so manual sweeps are easy.

## Sandbox and cleanup

Every run creates:
- a Drive folder `{prefix}-{YYYYMMDD-HHMMSS}-{short-uuid}` containing every
  Doc / Sheet / Form / file the run produces;
- a Gmail label `{prefix}` (idempotent — reused across runs);
- and tracks calendar events / Gmail messages by ID.

On teardown, the suite trashes every tracked resource and permanently deletes
the sandbox folder. Per-run reports land in
`_local/tests/live/.runs/{run_id}/`:

- `cleanup.json` — outcome of each teardown step.
- `leaked.json` — present only if teardown failed for any resource. Contains
  the IDs to clean up manually.
- `downloads/` — round-trip files from Drive download tests.

If a run is interrupted (SIGINT, network failure), some resources may leak.
Manual sweep:

```bash
uv run suitewright drive search "suitewright-live-test"
uv run suitewright gmail search "[suitewright-live-test]"
uv run suitewright calendar list --calendar primary --max 50 \
  | grep -i "suitewright-live-test"
```

The Forms cache directory (`cache/`) may keep stale entries for deleted forms.
They are harmless; clear with `rm cache/forms-*.json` if desired.

## Known gaps the suite works around

- `sheets` has no `create` command — fixtures create test sheets via
  `googleapiclient` directly inside the sandbox folder.
- `docs create` and `forms create` do not accept `--parent` — fixtures move the
  created resource into the sandbox folder via a Drive `files.update` call.
- `gmail` has no `labels create` — `conftest.py` creates the sandbox label via
  `googleapiclient` if it does not already exist.

These are the only places live tests bypass the CLI. They are test infrastructure,
not feature coverage.

## Troubleshooting

**Tests skip with "needs --run-live"** — pass `--run-live` to pytest.

**".env not found"** — run `uv run python tests/live/scripts/bootstrap.py` first.

**`AUTH_SCOPE_MISMATCH`** — your token is missing a scope suitewright requires.
Re-run `uv run python tests/live/scripts/bootstrap.py` (it will prompt for re-consent).

**`HttpError 403`** — confirm Gmail / Forms / Calendar / Drive APIs are enabled
in the GCP project that issued the client secret.

**Cleanup leaks** — read `_local/tests/live/.runs/{run_id}/leaked.json` and
delete the listed resources manually with `suitewright drive delete --permanent`,
`suitewright gmail trash`, or the appropriate command.

**Already-deleted calendar events in cleanup.json show ok:false** — this is
expected when a test deletes its own event and teardown retries the delete.
The 410 is swallowed silently; the resource is gone.
