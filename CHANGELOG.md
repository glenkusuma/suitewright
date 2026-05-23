# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2] - 2026-05-23

### Added

- Docs cache-first workflow: `docs cache fetch|show|validate|update`
- Docs query engine: 10 local inspection commands (`structure`, `get`, `list-headings`, `find-heading`, `section`, `find-text`, `get-range`, `word-count`, `find-citations`, `check-headings`)
- Docs mutate module: 9 guarded write commands with revisionId staleness checks (`append`, `replace`, `replace-all`, `insert-table`, `insert-image`, `style-range`, `table-update-cell`, `table-append-row`, `raw`)
- Shared `_core/` subpackage: `cache.py` (CacheStore), `output.py` (emit_json, error_exit, warn), extracted from inline implementations
- Update check: CLI prints a notice to stderr when a newer version is available on PyPI (cached 24h, disable with `SUITEWRIGHT_NO_UPDATE_CHECK=1`)
- Live e2e tests for docs cache workflow (smoke, mutate, e2e tiers)
- Hypothesis property tests for cache hash, text extraction, heading enumeration, word count consistency
- `docs/` directory with developer documentation (development, docker, configuration)
- `CHANGELOG.md`
- `scripts/check_version.py` for CI version consistency checks

### Changed

- CLI restructured: docs commands now use grouped subparsers (`docs cache`, `docs query`, `docs mutate`, `docs table`)
- Internal modules moved to `src/suitewright/_core/` (paths, auth, service, retry, render)
- Re-export shim files removed - all imports now use `suitewright._core.*` directly
- Environment variables renamed for clarity: `SUITEWRIGHT_TOKEN` -> `SUITEWRIGHT_TOKEN_PATH`, `SUITEWRIGHT_CLIENT_SECRET` -> `SUITEWRIGHT_CLIENT_SECRET_PATH`
- README restructured for PyPI (user-facing only, internals moved to docs/)
- Skill reference updated for new CLI tree
- Docker publish workflow: build and push separated, Trivy scan runs before push, push requires environment approval

### Removed

- `src/suitewright/docs/basic.py` (functionality moved to mutate.py)
- `src/suitewright/docs/semantic.py` (functionality moved to mutate.py)
- Thin re-export shim files at `src/suitewright/{auth,paths,service,render,retry}.py`

### Breaking Changes

- `docs append` -> `docs mutate append`
- `docs replace` -> `docs mutate replace`
- `docs show-structure` -> `docs query structure`
- `docs get` -> `docs query get`
- `docs update` -> `docs cache update`
- `docs table-get` -> `docs table get`
- `docs insert-table` -> `docs mutate insert-table`
- `docs insert-image` -> `docs mutate insert-image`
- `docs style-range` -> `docs mutate style-range`
- `docs table-update-cell` -> `docs mutate table-update-cell`
- `docs table-append-row` -> `docs mutate table-append-row`
- `docs replace-all` -> `docs mutate replace-all`
- `from suitewright.service import ...` -> `from suitewright._core.service import ...`
- `SUITEWRIGHT_TOKEN` env var -> `SUITEWRIGHT_TOKEN_PATH`
- `SUITEWRIGHT_CLIENT_SECRET` env var -> `SUITEWRIGHT_CLIENT_SECRET_PATH`

## [0.0.1rc1] - 2026-05-19

### Added

- Initial release candidate
- Gmail: search, get, send, reply, labels, modify, trash
- Calendar: list, create, delete
- Drive: search, get, upload, download, create-folder, share, delete
- Contacts: list
- Sheets: get, update, append
- Docs: create, append, replace, update, show-structure, table-get, table-update-cell, table-append-row, comments, plan, request-template
- Forms: list, get, create, update, fetch, show-cache, validate, cache-update, query helpers
- Auth: init, login, check, revoke (4-mode path resolution)
- Docker: hardened runtime image with Trivy scanning
- CI: multi-platform testing (Linux, macOS, Windows), security scanning
