# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org).

**Guiding Principles:**

- Changelogs are for humans, not machines.
- There should be an entry for every version.
- The same types of changes should be grouped.
- Versions and sections should be linkable.
- The latest version comes first.
- The release date of each version is displayed.

## [Unreleased]

## [0.0.1-rc] - 2026-05-20

### Added

- Multi-service CLI covering Gmail, Calendar, Drive, Docs, Sheets, Contacts, and Forms
- Cache-first workflow for Forms (fetch remote state, inspect locally, apply guarded mutations)
- Agent-friendly JSON output with explicit auth paths and no hidden global state
- 4-mode auth resolution system (`env` -> `xdg` -> `dev` -> `default`) with repo-root `auth/` banned
- Hardened Docker images with digest-pinned bases, non-root user, read-only filesystem, and `cap-drop=ALL`
- Docker dev workflow script (`scripts/docker.py`) for contributor-friendly test execution with `build` and `test` subcommands
- Full CI/CD pipeline with lint, type check, unit tests, security scanning, Docker build/scan, and release automation
- Security tooling including SHA-pinned GitHub Actions, gitleaks, pip-audit, bandit, Trivy, and CodeQL
- OIDC-based PyPI publishing with attestations
- Organized test layout: `tests/unit/`, `tests/integration/`, `tests/scripts/`, `tests/live/`

[unreleased]: https://github.com/glenkusuma/suitewright/compare/v0.0.1-rc...HEAD
[0.0.1-rc]: https://github.com/glenkusuma/suitewright/releases/tag/v0.0.1-rc
