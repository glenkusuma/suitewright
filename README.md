# suitewright

**A portable Google Workspace CLI and workflow toolkit for humans and agents.**

> Early development (pre-0.1.0). Commands and APIs may have breaking changes between minor versions. Pin your version if stability matters.

`suitewright` is a Python command-line tool for working with Google Workspace from a local machine, automation script, or AI agent runtime. It is framework-neutral and built around a cache-first workflow that both humans and agents can inspect.

## Installation

With `uv`:

```bash
uv tool install suitewright
```

With `pip`:

```bash
python3 -m pip install suitewright
```

From a checkout:

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

`suitewright` uses local OAuth credentials. Provide your Google OAuth client secret, complete browser-based consent once, and the resulting token is stored locally.

```bash
suitewright auth init --client-secret /path/to/client_secret.json
suitewright auth login
suitewright auth check
```

For the full auth setup guide (headless flows, Advanced Protection, troubleshooting), see the [skill reference](https://github.com/glenkusuma/suitewright/blob/main/skills/suitewright-google-workspace/SKILL.md).

## Command surface

```text
suitewright auth          init | login | check | revoke | install-deps
suitewright gmail         search | get | send | reply | labels | modify | trash
suitewright calendar      list | create | delete
suitewright drive         search | get | upload | download | create-folder | share | delete
suitewright contacts      list
suitewright sheets        get | update | append
suitewright docs          cache fetch | show | validate | update
                          query structure | get | list-headings | find-heading | section
                                find-text | get-range | word-count | find-citations | check-headings
                          mutate append | replace | replace-all | insert-table | insert-image
                                 style-range | table-update-cell | table-append-row | raw
                          table get
                          plan | request-template <kind> | comments list | get | reply | resolve
                          create
suitewright forms         list | get | create | update
                          fetch | show-cache | validate | cache-update
                          query locate | query after | query delete-request
                          query get-item | query neighbors | query section | query indexer
```

Run any subcommand with `--help` for full flags.

## Examples

### Gmail

```bash
suitewright gmail search "is:unread" --max 10
suitewright gmail get MESSAGE_ID
suitewright gmail send --to user@example.com --subject "Hello" --body "Message text"
```

### Calendar

```bash
suitewright calendar list --calendar primary
suitewright calendar create --calendar primary --summary "Standup" \
  --start 2026-03-01T10:00:00-06:00 --end 2026-03-01T10:30:00-06:00
```

### Drive

```bash
suitewright drive search "quarterly report" --max 10
suitewright drive upload report.pdf --parent FOLDER_ID
suitewright drive delete FILE_ID                # moves to trash
suitewright drive delete FILE_ID --permanent    # irreversible
```

### Docs - cache-first workflow

```bash
suitewright docs cache fetch DOC_ID
suitewright docs query structure DOC_ID --full-text
suitewright docs query find-text DOC_ID --pattern "typo"
suitewright docs mutate replace-all DOC_ID --find "typo" --replace "fixed" --dry-run
suitewright docs mutate replace-all DOC_ID --find "typo" --replace "fixed"
suitewright docs cache validate DOC_ID
```

### Forms - cache-first workflow

```bash
suitewright forms fetch FORM_ID
suitewright forms query locate FORM_ID --title "Question 1"
suitewright forms cache-update FORM_ID /path/to/changes.json
```

### Sheets

```bash
suitewright sheets get SHEET_ID "Sheet1!A1:D10"
suitewright sheets update SHEET_ID "Sheet1!A1:B2" --values '[["Name","Score"],["Alice","95"]]'
suitewright sheets append SHEET_ID "Sheet1!A:C" --values '[["new","row","data"]]'
```

## Cache-first philosophy

suitewright is designed around a cache-first pattern: fetch remote state once, inspect and plan locally, then apply a guarded mutation and refresh. This pattern is implemented for both Forms (`forms fetch` -> `forms query` -> `forms cache-update`) and Docs (`docs cache fetch` -> `docs query` -> `docs mutate` -> `docs cache validate`). Local artifacts can be opened in an editor, read by an agent, committed to a branch, diffed, or fed into a repeatable script.

## Contributing

See [docs/](https://github.com/glenkusuma/suitewright/tree/main/docs) for developer documentation:

- [Development](https://github.com/glenkusuma/suitewright/blob/main/docs/development.md) - dev setup, testing, linting
- [Docker](https://github.com/glenkusuma/suitewright/blob/main/docs/docker.md) - hardened runtime, compose, dev workflow
- [Configuration](https://github.com/glenkusuma/suitewright/blob/main/docs/configuration.md) - auth resolution, env vars

## License

Apache-2.0. See [LICENSE](https://github.com/glenkusuma/suitewright/blob/main/LICENSE) and [NOTICE](https://github.com/glenkusuma/suitewright/blob/main/NOTICE) for details.
