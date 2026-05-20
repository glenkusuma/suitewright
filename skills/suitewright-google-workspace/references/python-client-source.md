# Python client source

suitewright is built on Google's official Python client libraries.

Primary upstream reference:
- https://github.com/googleapis/google-api-python-client

Required Python packages (installed automatically with suitewright):
- `google-api-python-client>=2.194.0`
- `google-auth-oauthlib>=1.3.1`
- `google-auth-httplib2>=0.3.1`

**Python version requirement:** 3.11 or later.

## Installing suitewright

With `uv` (recommended):

```bash
uv tool install suitewright
```

With `pip`:

```bash
pip install suitewright
```

Add to a project managed with uv:

```bash
uv add suitewright
```

From a checkout (development mode):

```bash
git clone https://github.com/glenkusuma/suitewright.git
cd suitewright
uv sync
uv run suitewright --help
```
