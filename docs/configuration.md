# Configuration

## Auth resolution

Auth file resolution follows a 4-mode precedence (highest wins):

| Priority | Mode | Source |
|----------|------|--------|
| 1 | `env` | `SUITEWRIGHT_TOKEN_PATH` / `SUITEWRIGHT_CLIENT_SECRET_PATH` env vars |
| 2 | `xdg` | `$XDG_CONFIG_HOME/suitewright/auth/` |
| 3 | `dev` | `SUITEWRIGHT_AUTH_DIR` (default `../suitewright-auth` relative to repo root) |
| 4 | `default` | `$HOME/.config/suitewright/auth/` |

Run `suitewright auth check --json` to see which mode is active. The output includes a `"mode"` field with one of: `"env"`, `"xdg"`, `"dev"`, `"default"`.

## Cache resolution

- `SUITEWRIGHT_CACHE_DIR` env var (if set)
- `$XDG_CACHE_HOME/suitewright/` (default `~/.cache/suitewright/`)

## Dev mode and SUITEWRIGHT_AUTH_DIR

In development, auth files are read from `SUITEWRIGHT_AUTH_DIR`. This defaults to `../suitewright-auth` relative to the detected repo root.

```bash
export SUITEWRIGHT_AUTH_DIR=/path/to/suitewright-auth
suitewright auth check --json  # confirms mode: "dev"
```

## Environment variables reference

| Variable | Purpose |
|----------|---------|
| `SUITEWRIGHT_TOKEN_PATH` | Path to OAuth token JSON (overrides all other resolution) |
| `SUITEWRIGHT_CLIENT_SECRET_PATH` | Path to client secret JSON (overrides all other resolution) |
| `SUITEWRIGHT_AUTH_DIR` | Directory containing auth files (dev mode) |
| `SUITEWRIGHT_CACHE_DIR` | Directory for local cache artifacts |
| `XDG_CONFIG_HOME` | XDG base directory for config (default `~/.config`) |
| `XDG_CACHE_HOME` | XDG base directory for cache (default `~/.cache`) |
