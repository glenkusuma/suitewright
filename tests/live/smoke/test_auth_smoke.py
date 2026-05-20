import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.smoke]


def test_auth_check_authenticated(sandbox):
    result = cli_run(["auth", "check"])
    assert result["status"] == "AUTHENTICATED"
    assert result["tokenExists"] is True
    assert result["mode"] in {"dev", "xdg", "env"}


def test_auth_check_path_resolution(sandbox):
    result = cli_run(["auth", "check"])
    for key in ("root", "token", "client_secret", "cache_dir"):
        assert result.get(key)
