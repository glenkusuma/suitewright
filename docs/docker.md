# Docker

A hardened Docker image is available for running suitewright in production or CI environments.

## Hardened runtime

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

## Auth mount

Auth files are mounted into the `auth/` subdir only - never over the entire config directory. This limits the container's read access to credentials only:

```bash
-v /path/to/suitewright-auth:/home/suitewright/.config/suitewright/auth:ro
```

The source path is controlled by `SUITEWRIGHT_AUTH_DIR`. The mount is read-only (`:ro`).

## docker-compose

The included `docker-compose.yml` configures both the runtime and test services with the same hardening. Auth is sourced from `SUITEWRIGHT_AUTH_DIR`:

```bash
SUITEWRIGHT_AUTH_DIR=/path/to/suitewright-auth docker compose up suitewright
```

## Dev workflow script

A contributor-friendly wrapper script handles building the test image and running tests in Docker:

```bash
uv run python scripts/docker.py build              # build test image
uv run python scripts/docker.py test               # run unit/integration tests
uv run python scripts/docker.py test --live        # run live API tests (with preflight checks)
uv run python scripts/docker.py test -k test_auth  # forward args to pytest
```
