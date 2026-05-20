"""Tests for suitewright.paths resolution logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from suitewright import paths


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for var in (
        "SUITEWRIGHT_ROOT",
        "SUITEWRIGHT_TOKEN",
        "SUITEWRIGHT_CLIENT_SECRET",
        "SUITEWRIGHT_CACHE_DIR",
        "SUITEWRIGHT_AUTH_DIR",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
    ):
        monkeypatch.delenv(var, raising=False)


class TestReadPyprojectName:
    def test_reads_name(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text('[project]\nname = "suitewright"\nversion = "0.0.1"\n')
        assert paths._read_pyproject_name(p) == "suitewright"

    def test_missing_file(self, tmp_path):
        assert paths._read_pyproject_name(tmp_path / "missing.toml") is None

    def test_no_name_field(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text('[project]\nversion = "0.0.1"\n')
        assert paths._read_pyproject_name(p) is None

    def test_quoted_name(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text("[project]\nname = 'mypackage'\n")
        assert paths._read_pyproject_name(p) == "mypackage"


class TestEnvVarOverrides:
    def test_token_env_var(self, monkeypatch, tmp_path):
        token = tmp_path / "my_token.json"
        monkeypatch.setenv("SUITEWRIGHT_TOKEN", str(token))
        assert paths.resolve("token") == token

    def test_client_secret_env_var(self, monkeypatch, tmp_path):
        cs = tmp_path / "secret.json"
        monkeypatch.setenv("SUITEWRIGHT_CLIENT_SECRET", str(cs))
        assert paths.resolve("client_secret") == cs

    def test_cache_dir_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SUITEWRIGHT_CACHE_DIR", str(tmp_path))
        assert paths.resolve("cache_dir") == tmp_path

    def test_root_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SUITEWRIGHT_ROOT", str(tmp_path))
        assert paths.resolve("root") == tmp_path
        assert paths.resolve("token") == tmp_path / "auth" / "google_token.json"
        assert paths.resolve("client_secret") == tmp_path / "auth" / "google_client_secret.json"
        assert paths.resolve("cache_dir") == tmp_path / "cache"


class TestXDGDefaults:
    def test_token_xdg_default(self, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg_config")
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: None)
        result = paths.resolve("token")
        assert str(result) == "/tmp/xdg_config/suitewright/auth/google_token.json"

    def test_cache_dir_xdg_default(self, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/xdg_cache")
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: None)
        result = paths.resolve("cache_dir")
        assert str(result) == "/tmp/xdg_cache/suitewright"

    def test_token_home_fallback(self, monkeypatch):
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: None)
        result = paths.resolve("token")
        assert "suitewright" in str(result)
        assert result.name == "google_token.json"


class TestExists:
    def test_exists_true(self, monkeypatch, tmp_path):
        token = tmp_path / "google_token.json"
        token.write_text("{}")
        monkeypatch.setenv("SUITEWRIGHT_TOKEN", str(token))
        assert paths.exists("token") is True

    def test_exists_false(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SUITEWRIGHT_TOKEN", str(tmp_path / "missing.json"))
        assert paths.exists("token") is False


class TestDescribe:
    """Tests for describe() covering all 4 auth resolution modes."""

    def test_env_mode_with_root(self, monkeypatch, tmp_path):
        """Mode 'env' when SUITEWRIGHT_ROOT is set."""
        monkeypatch.setenv("SUITEWRIGHT_ROOT", str(tmp_path))
        info = paths.describe()
        assert info["mode"] == "env"
        assert info["root"] == str(tmp_path)
        assert info["token"] == str(tmp_path / "auth" / "google_token.json")
        assert info["client_secret"] == str(tmp_path / "auth" / "google_client_secret.json")
        assert info["cache_dir"] == str(tmp_path / "cache")
        assert "tokenExists" in info
        assert "clientSecretExists" in info

    def test_env_mode_with_token(self, monkeypatch, tmp_path):
        """Mode 'env' when SUITEWRIGHT_TOKEN is set."""
        token_path = tmp_path / "my_token.json"
        token_path.write_text("{}")
        monkeypatch.setenv("SUITEWRIGHT_TOKEN", str(token_path))
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: None)
        info = paths.describe()
        assert info["mode"] == "env"
        assert info["tokenExists"] is True

    def test_env_mode_with_client_secret(self, monkeypatch, tmp_path):
        """Mode 'env' when SUITEWRIGHT_CLIENT_SECRET is set."""
        cs_path = tmp_path / "secret.json"
        cs_path.write_text("{}")
        monkeypatch.setenv("SUITEWRIGHT_CLIENT_SECRET", str(cs_path))
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: None)
        info = paths.describe()
        assert info["mode"] == "env"
        assert info["clientSecretExists"] is True

    def test_env_mode_with_cache_dir(self, monkeypatch, tmp_path):
        """Mode 'env' when SUITEWRIGHT_CACHE_DIR is set."""
        monkeypatch.setenv("SUITEWRIGHT_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: None)
        info = paths.describe()
        assert info["mode"] == "env"
        assert info["cache_dir"] == str(tmp_path / "cache")

    def test_xdg_mode(self, monkeypatch, tmp_path):
        """Mode 'xdg' when XDG_CONFIG_HOME is explicitly set."""
        xdg_config = tmp_path / "xdg_config"
        xdg_cache = tmp_path / "xdg_cache"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
        monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: None)
        info = paths.describe()
        assert info["mode"] == "xdg"
        assert info["root"] == str(xdg_config / "suitewright")
        assert info["token"] == str(xdg_config / "suitewright" / "auth" / "google_token.json")
        assert info["client_secret"] == str(
            xdg_config / "suitewright" / "auth" / "google_client_secret.json"
        )
        assert info["cache_dir"] == str(xdg_cache / "suitewright")

    def test_dev_mode_with_auth_dir_env(self, monkeypatch, tmp_path):
        """Mode 'dev' when SUITEWRIGHT_AUTH_DIR is set and dev root detected."""
        auth_dir = tmp_path / "suitewright-auth"
        auth_dir.mkdir()
        dev_root = tmp_path / "project"
        dev_root.mkdir()
        monkeypatch.setenv("SUITEWRIGHT_AUTH_DIR", str(auth_dir))
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: dev_root)
        info = paths.describe()
        assert info["mode"] == "dev"
        assert info["root"] == str(dev_root)
        assert info["token"] == str(auth_dir / "google_token.json")
        assert info["client_secret"] == str(auth_dir / "google_client_secret.json")

    def test_dev_mode_with_default_auth_dir(self, monkeypatch, tmp_path):
        """Mode 'dev' when dev root is detected (uses default ../suitewright-auth)."""
        dev_root = tmp_path / "project"
        dev_root.mkdir()
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: dev_root)
        info = paths.describe()
        assert info["mode"] == "dev"
        assert info["root"] == str(dev_root)
        expected_auth = (dev_root / ".." / "suitewright-auth").resolve()
        assert info["token"] == str(expected_auth / "google_token.json")
        assert info["client_secret"] == str(expected_auth / "google_client_secret.json")

    def test_default_mode(self, monkeypatch, tmp_path):
        """Mode 'default' when no env vars set and no dev root detected."""
        monkeypatch.setattr(paths, "_detect_dev_root", lambda: None)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        info = paths.describe()
        assert info["mode"] == "default"
        assert info["root"] == str(tmp_path / ".config" / "suitewright")
        assert info["token"] == str(
            tmp_path / ".config" / "suitewright" / "auth" / "google_token.json"
        )
        assert info["client_secret"] == str(
            tmp_path / ".config" / "suitewright" / "auth" / "google_client_secret.json"
        )
        assert info["cache_dir"] == str(tmp_path / ".cache" / "suitewright")
        assert info["tokenExists"] is False
        assert info["clientSecretExists"] is False
