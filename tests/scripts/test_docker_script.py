"""Property-based tests for scripts/docker.py.

Feature: docker-dev-workflow, Property 1: Exit code propagation
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Add scripts directory to path so we can import docker module
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import docker


class TestExitCodePropagation:
    """Property 1: Exit code propagation.

    For any exit code (0-255) returned by the underlying Docker command,
    the script SHALL return that same exit code as its own exit code.

    **Validates: Requirements 1.4, 2.13**
    """

    @given(exit_code=st.integers(min_value=0, max_value=255))
    @settings(max_examples=100)
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_cmd_build_propagates_exit_code(
        self, mock_run: MagicMock, mock_check_docker: MagicMock, exit_code: int
    ) -> None:
        """cmd_build() returns the same exit code as the docker build subprocess."""
        mock_check_docker.return_value = None
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "build"], returncode=exit_code
        )

        result = docker.cmd_build()

        assert result == exit_code

    @given(exit_code=st.integers(min_value=0, max_value=255))
    @settings(max_examples=100)
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_cmd_test_propagates_exit_code(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        exit_code: int,
    ) -> None:
        """cmd_test([]) returns the same exit code as the docker run subprocess."""
        mock_check_docker.return_value = None
        mock_check_image.return_value = None
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "run"], returncode=exit_code
        )

        result = docker.cmd_test([])

        assert result == exit_code


class TestArgumentForwarding:
    """Property 2: Argument forwarding preserves all arguments.

    **Validates: Requirements 2.10**

    For any list of additional command-line arguments passed after `test`
    (and after consuming `--live` if present), all remaining arguments appear
    in the constructed Docker run command in the same order, appended after
    the default pytest arguments.
    """

    # Strategy: generate lists of printable strings that are not "--live"
    # and don't contain null bytes (which would break subprocess args)
    _arg_strategy = st.lists(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_characters="\x00",
            ),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s != "--live"),
        min_size=0,
        max_size=10,
    )

    @settings(max_examples=100)
    @given(args=_arg_strategy)
    def test_all_args_forwarded_in_order_default_mode(self, args: list[str]) -> None:
        """For any list of args not containing --live, all args appear in the
        subprocess command in order after the default pytest args.

        Feature: docker-dev-workflow, Property 2: Argument forwarding preserves all arguments
        """
        captured_cmd = None

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            result = MagicMock()
            result.returncode = 0
            return result

        with (
            patch("docker.check_docker"),
            patch("docker.check_image"),
            patch("docker.subprocess.run", side_effect=mock_subprocess_run),
        ):
            docker.cmd_test(args)

        # The command should end with: "pytest", "tests/", "--ignore=tests/live",
        # "--ignore=tests/scripts", *args
        assert captured_cmd is not None
        # Find where pytest args start
        pytest_idx = captured_cmd.index("pytest")
        pytest_section = captured_cmd[pytest_idx:]

        # Default pytest args
        default_pytest_args = [
            "pytest",
            "tests/",
            "--ignore=tests/live",
            "--ignore=tests/scripts",
        ]
        assert pytest_section[: len(default_pytest_args)] == default_pytest_args

        # All forwarded args should appear after the defaults, in order
        forwarded = pytest_section[len(default_pytest_args) :]
        assert forwarded == args

    @settings(max_examples=100)
    @given(args=_arg_strategy)
    def test_live_flag_consumed_and_rest_forwarded(self, args: list[str]) -> None:
        """When --live is mixed in with other args, it is consumed and the rest
        are forwarded to pytest in order.

        Feature: docker-dev-workflow, Property 2: Argument forwarding preserves all arguments
        """
        captured_cmd = None

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            result = MagicMock()
            result.returncode = 0
            return result

        # Insert --live at the front among the args
        args_with_live = ["--live", *args]

        with (
            patch("docker.check_docker"),
            patch("docker.check_image"),
            patch("docker.subprocess.run", side_effect=mock_subprocess_run),
            patch("docker.run_preflight"),
            patch.object(Path, "mkdir"),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "is_file", return_value=True),
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": "/tmp/fake-auth"}),
        ):
            docker.cmd_test(args_with_live)

        # The command should end with: "pytest", "tests/live/", "--run-live", *args
        assert captured_cmd is not None
        pytest_idx = captured_cmd.index("pytest")
        pytest_section = captured_cmd[pytest_idx:]

        # Live mode default pytest args are: "pytest", "tests/live/", "--run-live"
        default_live_args = ["pytest", "tests/live/", "--run-live"]
        assert pytest_section[: len(default_live_args)] == default_live_args

        # All forwarded args (without --live) should appear after the defaults, in order
        forwarded = pytest_section[len(default_live_args) :]
        assert forwarded == args

    @settings(max_examples=100)
    @given(
        args=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "S"),
                    blacklist_characters="\x00",
                ),
                min_size=1,
                max_size=50,
            ).filter(lambda s: s != "--live"),
            min_size=1,
            max_size=10,
        ),
        live_count=st.integers(min_value=1, max_value=3),
    )
    def test_multiple_live_flags_all_consumed(self, args: list[str], live_count: int) -> None:
        """When multiple --live flags appear, all are consumed and only non-live
        args are forwarded.

        Feature: docker-dev-workflow, Property 2: Argument forwarding preserves all arguments
        """
        captured_cmd = None

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            result = MagicMock()
            result.returncode = 0
            return result

        # Insert multiple --live flags
        args_with_lives = ["--live"] * live_count + args

        with (
            patch("docker.check_docker"),
            patch("docker.check_image"),
            patch("docker.subprocess.run", side_effect=mock_subprocess_run),
            patch("docker.run_preflight"),
            patch.object(Path, "mkdir"),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "is_file", return_value=True),
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": "/tmp/fake-auth"}),
        ):
            docker.cmd_test(args_with_lives)

        assert captured_cmd is not None
        # Verify no --live appears in the final command
        assert "--live" not in captured_cmd
        # Verify all non-live args are forwarded
        pytest_idx = captured_cmd.index("pytest")
        pytest_section = captured_cmd[pytest_idx:]
        default_live_args = ["pytest", "tests/live/", "--run-live"]
        forwarded = pytest_section[len(default_live_args) :]
        assert forwarded == args


# =============================================================================
# Unit Tests for scripts/docker.py
# =============================================================================


class TestCheckDocker:
    """Unit tests for check_docker() prerequisite validation."""

    @patch("docker.subprocess.run")
    @patch("docker.shutil.which", return_value=None)
    def test_exits_when_docker_not_on_path(
        self, mock_which: MagicMock, mock_run: MagicMock, capsys
    ) -> None:
        """check_docker() exits with code 1 when docker is not found on PATH."""
        with pytest.raises(SystemExit) as exc_info:
            docker.check_docker()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Docker not found" in captured.err
        assert "docker:" in captured.err
        assert "Install Docker" in captured.err

    @patch("docker.subprocess.run")
    @patch("docker.shutil.which", return_value="/usr/bin/docker")
    def test_exits_when_daemon_not_running(
        self, mock_which: MagicMock, mock_run: MagicMock, capsys
    ) -> None:
        """check_docker() exits with code 1 when docker daemon is not running."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=1, stdout="", stderr=""
        )
        with pytest.raises(SystemExit) as exc_info:
            docker.check_docker()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "daemon" in captured.err.lower()
        assert "docker:" in captured.err

    @patch("docker.subprocess.run")
    @patch("docker.shutil.which", return_value="/usr/bin/docker")
    def test_passes_when_docker_available_and_running(
        self, mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        """check_docker() does not exit when docker is available and daemon is running."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=0, stdout="", stderr=""
        )
        # Should not raise
        docker.check_docker()
        mock_which.assert_called_once_with("docker")
        mock_run.assert_called_once()


class TestCheckImage:
    """Unit tests for check_image() prerequisite validation."""

    @patch("docker.subprocess.run")
    def test_exits_when_image_not_found(self, mock_run: MagicMock, capsys) -> None:
        """check_image() exits with code 1 when the test image does not exist."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "image", "inspect"], returncode=1, stdout="", stderr=""
        )
        with pytest.raises(SystemExit) as exc_info:
            docker.check_image()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "suitewright-test:local" in captured.err
        assert "docker:" in captured.err
        assert "Build first" in captured.err

    @patch("docker.subprocess.run")
    def test_passes_when_image_exists(self, mock_run: MagicMock) -> None:
        """check_image() does not exit when the test image exists locally."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "image", "inspect"], returncode=0, stdout="", stderr=""
        )
        # Should not raise
        docker.check_image()
        mock_run.assert_called_once()


class TestCmdBuild:
    """Unit tests for cmd_build() subcommand."""

    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_constructs_correct_docker_build_command(
        self, mock_run: MagicMock, mock_check_docker: MagicMock
    ) -> None:
        """cmd_build() constructs the correct docker build command."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.cmd_build()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "docker"
        assert cmd[1] == "build"
        assert "-t" in cmd
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "suitewright-test:local"
        assert "-f" in cmd
        f_idx = cmd.index("-f")
        assert cmd[f_idx + 1] == "Dockerfile.test"
        assert cmd[-1] == "."

    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_prints_confirmation_on_success(
        self, mock_run: MagicMock, mock_check_docker: MagicMock, capsys
    ) -> None:
        """cmd_build() prints confirmation message to stderr on success."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.cmd_build()
        captured = capsys.readouterr()
        assert "suitewright-test" in captured.err
        assert "local" in captured.err
        assert "docker:" in captured.err
        assert captured.out == ""

    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_no_confirmation_on_failure(
        self, mock_run: MagicMock, mock_check_docker: MagicMock, capsys
    ) -> None:
        """cmd_build() does not print confirmation when build fails."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1)
        result = docker.cmd_build()
        assert result == 1
        captured = capsys.readouterr()
        assert "Image built" not in captured.err

    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_propagates_exit_code(self, mock_run: MagicMock, mock_check_docker: MagicMock) -> None:
        """cmd_build() propagates Docker build exit code."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=125)
        result = docker.cmd_build()
        assert result == 125

    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_runs_from_repo_root(self, mock_run: MagicMock, mock_check_docker: MagicMock) -> None:
        """cmd_build() runs docker build from the repo root directory."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.cmd_build()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == str(docker.REPO_ROOT)


class TestCmdTestDefault:
    """Unit tests for cmd_test() in default mode (no --live flag)."""

    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_constructs_correct_default_docker_run_command(
        self, mock_run: MagicMock, mock_check_docker: MagicMock, mock_check_image: MagicMock
    ) -> None:
        """cmd_test([]) constructs the correct docker run command for default mode."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.cmd_test([])
        cmd = mock_run.call_args[0][0]
        assert cmd[0:2] == ["docker", "run"]
        assert "--rm" in cmd
        assert "--name" in cmd
        name_idx = cmd.index("--name")
        assert cmd[name_idx + 1] == "suitewright-test"
        assert "suitewright-test:local" in cmd
        # Verify tests volume mount
        volume_args = [cmd[i + 1] for i, v in enumerate(cmd) if v == "-v"]
        tests_mount = [v for v in volume_args if "/app/tests:ro" in v]
        assert len(tests_mount) == 1
        # Verify pytest command
        pytest_idx = cmd.index("pytest")
        assert cmd[pytest_idx + 1] == "tests/"
        assert cmd[pytest_idx + 2] == "--ignore=tests/live"
        assert cmd[pytest_idx + 3] == "--ignore=tests/scripts"

    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_forwards_extra_args_to_pytest(
        self, mock_run: MagicMock, mock_check_docker: MagicMock, mock_check_image: MagicMock
    ) -> None:
        """cmd_test() forwards extra arguments to pytest after defaults."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.cmd_test(["-v", "-m", "smoke", "--tb=short"])
        cmd = mock_run.call_args[0][0]
        pytest_idx = cmd.index("pytest")
        pytest_section = cmd[pytest_idx:]
        assert "-v" in pytest_section
        assert "-m" in pytest_section
        assert "smoke" in pytest_section
        assert "--tb=short" in pytest_section

    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_propagates_pytest_exit_code(
        self, mock_run: MagicMock, mock_check_docker: MagicMock, mock_check_image: MagicMock
    ) -> None:
        """cmd_test([]) propagates the pytest exit code."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=5)
        result = docker.cmd_test([])
        assert result == 5

    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_no_env_vars_in_default_mode(
        self, mock_run: MagicMock, mock_check_docker: MagicMock, mock_check_image: MagicMock
    ) -> None:
        """cmd_test([]) does not set environment variables in default mode."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.cmd_test([])
        cmd = mock_run.call_args[0][0]
        assert "-e" not in cmd

    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_only_tests_volume_in_default_mode(
        self, mock_run: MagicMock, mock_check_docker: MagicMock, mock_check_image: MagicMock
    ) -> None:
        """cmd_test([]) only mounts the tests directory in default mode."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.cmd_test([])
        cmd = mock_run.call_args[0][0]
        volume_flags = [i for i, v in enumerate(cmd) if v == "-v"]
        assert len(volume_flags) == 1


class TestCmdTestLive:
    """Unit tests for cmd_test() in live mode (--live flag)."""

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_constructs_correct_live_docker_run_command(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
    ) -> None:
        """cmd_test(['--live']) constructs the correct docker run command for live mode."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir()

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": str(auth_dir)}),
            patch.object(Path, "is_file", return_value=True),
        ):
            docker.cmd_test(["--live"])

        cmd = mock_run.call_args[0][0]
        assert cmd[0:2] == ["docker", "run"]
        assert "--rm" in cmd
        name_idx = cmd.index("--name")
        assert cmd[name_idx + 1] == "suitewright-test-live"
        assert "suitewright-test:local" in cmd
        # Verify pytest command for live mode
        pytest_idx = cmd.index("pytest")
        assert cmd[pytest_idx + 1] == "tests/live/"
        assert cmd[pytest_idx + 2] == "--run-live"

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_live_flag_not_forwarded_to_pytest(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
    ) -> None:
        """--live flag is consumed by the script and not forwarded to pytest."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir()

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": str(auth_dir)}),
            patch.object(Path, "is_file", return_value=True),
        ):
            docker.cmd_test(["--live", "-v", "--tb=short"])

        cmd = mock_run.call_args[0][0]
        assert "--live" not in cmd

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_live_mode_volume_mounts(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
    ) -> None:
        """Live mode mounts all required volumes with correct permissions."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir()

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": str(auth_dir)}),
            patch.object(Path, "is_file", return_value=True),
        ):
            docker.cmd_test(["--live"])

        cmd = mock_run.call_args[0][0]
        # Collect all volume mount arguments
        volume_args = []
        for i, arg in enumerate(cmd):
            if arg == "-v" and i + 1 < len(cmd):
                volume_args.append(cmd[i + 1])

        # Should have 5 volume mounts in live mode
        assert len(volume_args) == 5
        # tests:ro
        assert any("/app/tests:ro" in v for v in volume_args)
        # auth:ro
        assert any("/app/suitewright-auth:ro" in v for v in volume_args)
        # .env:ro
        assert any("/app/.env:ro" in v for v in volume_args)
        # cache (writable - no :ro suffix)
        cache_mounts = [v for v in volume_args if "/app/cache" in v]
        assert len(cache_mounts) == 1
        assert not cache_mounts[0].endswith(":ro")
        # _local (writable - no :ro suffix)
        local_mounts = [v for v in volume_args if "/app/_local" in v]
        assert len(local_mounts) == 1
        assert not local_mounts[0].endswith(":ro")

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_live_mode_env_vars(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
    ) -> None:
        """Live mode sets SUITEWRIGHT_AUTH_DIR and NO_COLOR env vars in container."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir()

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": str(auth_dir)}),
            patch.object(Path, "is_file", return_value=True),
        ):
            docker.cmd_test(["--live"])

        cmd = mock_run.call_args[0][0]
        # Collect all -e arguments
        env_args = []
        for i, arg in enumerate(cmd):
            if arg == "-e" and i + 1 < len(cmd):
                env_args.append(cmd[i + 1])

        assert "SUITEWRIGHT_AUTH_DIR=/app/suitewright-auth" in env_args
        assert "NO_COLOR=1" in env_args

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_live_mode_creates_cache_dir(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
    ) -> None:
        """Live mode creates ./cache directory if it does not exist."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir()

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": str(auth_dir)}),
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "mkdir") as mock_mkdir,
        ):
            docker.cmd_test(["--live"])

        # mkdir should have been called for cache and _local
        mkdir_calls = mock_mkdir.call_args_list
        assert len(mkdir_calls) >= 2

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_live_mode_exits_when_auth_dir_missing(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
        capsys,
    ) -> None:
        """Live mode exits with error when auth directory does not exist."""
        nonexistent_auth = tmp_path / "nonexistent"

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": str(nonexistent_auth)}),
            pytest.raises(SystemExit) as exc_info,
        ):
            docker.cmd_test(["--live"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Auth directory" in captured.err or "not found" in captured.err
        assert "docker:" in captured.err

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_live_mode_exits_when_env_file_missing(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
        capsys,
    ) -> None:
        """Live mode exits with error when .env file does not exist."""
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir()

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": str(auth_dir)}),
            patch.object(Path, "is_file", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            docker.cmd_test(["--live"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert ".env" in captured.err
        assert "docker:" in captured.err


class TestRunPreflight:
    """Unit tests for run_preflight() function."""

    @patch("docker.subprocess.run")
    def test_calls_preflight_scripts_in_order(self, mock_run: MagicMock) -> None:
        """run_preflight() calls both preflight scripts in the correct order."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.run_preflight()
        assert mock_run.call_count == 2
        first_call = mock_run.call_args_list[0][0][0]
        second_call = mock_run.call_args_list[1][0][0]
        assert "preflight.py" in " ".join(first_call)
        assert "preflight-live.py" in " ".join(second_call)

    @patch("docker.subprocess.run")
    def test_preflight_runs_with_uv(self, mock_run: MagicMock) -> None:
        """run_preflight() invokes scripts via 'uv run python'."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.run_preflight()
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            assert cmd[0:3] == ["uv", "run", "python"]

    @patch("docker.subprocess.run")
    def test_preflight_failure_aborts_before_second_script(
        self, mock_run: MagicMock, capsys
    ) -> None:
        """run_preflight() aborts when first preflight script fails."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=2)
        with pytest.raises(SystemExit) as exc_info:
            docker.run_preflight()
        assert exc_info.value.code == 2
        # Only the first script should have been called
        assert mock_run.call_count == 1
        captured = capsys.readouterr()
        assert "preflight" in captured.err.lower()

    @patch("docker.subprocess.run")
    def test_second_preflight_failure_propagates(self, mock_run: MagicMock, capsys) -> None:
        """run_preflight() propagates exit code when second preflight fails."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0),
            subprocess.CompletedProcess(args=[], returncode=3),
        ]
        with pytest.raises(SystemExit) as exc_info:
            docker.run_preflight()
        assert exc_info.value.code == 3
        assert mock_run.call_count == 2

    @patch("docker.subprocess.run")
    def test_preflight_runs_from_repo_root(self, mock_run: MagicMock) -> None:
        """run_preflight() runs scripts from the repo root directory."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.run_preflight()
        for call in mock_run.call_args_list:
            kwargs = call[1]
            assert kwargs["cwd"] == str(docker.REPO_ROOT)

    @patch("docker.subprocess.run")
    def test_preflight_prints_status_messages(self, mock_run: MagicMock, capsys) -> None:
        """run_preflight() prints status messages to stderr."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        docker.run_preflight()
        captured = capsys.readouterr()
        assert "docker:" in captured.err
        assert "Running" in captured.err


class TestMainDispatch:
    """Unit tests for main() dispatch logic."""

    @patch("docker.sys.argv", ["docker.py"])
    def test_no_subcommand_prints_usage_and_exits(self, capsys) -> None:
        """main() prints usage and exits with code 1 when no subcommand given."""
        with pytest.raises(SystemExit) as exc_info:
            docker.main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage" in captured.err
        assert "build" in captured.err
        assert "test" in captured.err

    @patch("docker.sys.argv", ["docker.py", "unknown"])
    def test_unknown_subcommand_prints_usage_and_exits(self, capsys) -> None:
        """main() prints usage and exits with code 1 for unknown subcommand."""
        with pytest.raises(SystemExit) as exc_info:
            docker.main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Unknown subcommand" in captured.err
        assert "Usage" in captured.err

    @patch("docker.cmd_build", return_value=0)
    @patch("docker.sys.argv", ["docker.py", "build"])
    def test_dispatches_to_build(self, mock_build: MagicMock) -> None:
        """main() dispatches 'build' subcommand to cmd_build()."""
        with pytest.raises(SystemExit) as exc_info:
            docker.main()
        assert exc_info.value.code == 0
        mock_build.assert_called_once()

    @patch("docker.cmd_test", return_value=0)
    @patch("docker.sys.argv", ["docker.py", "test", "--live", "-v"])
    def test_dispatches_to_test_with_args(self, mock_test: MagicMock) -> None:
        """main() dispatches 'test' subcommand with extra args to cmd_test()."""
        with pytest.raises(SystemExit) as exc_info:
            docker.main()
        assert exc_info.value.code == 0
        mock_test.assert_called_once_with(["--live", "-v"])

    @patch("docker.cmd_build", return_value=42)
    @patch("docker.sys.argv", ["docker.py", "build"])
    def test_propagates_build_exit_code(self, mock_build: MagicMock) -> None:
        """main() propagates cmd_build() exit code via sys.exit."""
        with pytest.raises(SystemExit) as exc_info:
            docker.main()
        assert exc_info.value.code == 42

    @patch("docker.cmd_test", return_value=5)
    @patch("docker.sys.argv", ["docker.py", "test"])
    def test_propagates_test_exit_code(self, mock_test: MagicMock) -> None:
        """main() propagates cmd_test() exit code via sys.exit."""
        with pytest.raises(SystemExit) as exc_info:
            docker.main()
        assert exc_info.value.code == 5


class TestMessageFormatting:
    """Unit tests for msg() and err() message formatting."""

    def test_msg_writes_to_stderr_with_prefix(self, capsys) -> None:
        """msg() writes to stderr with 'docker:' prefix."""
        docker.msg("hello world")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "docker: hello world\n"

    def test_err_writes_to_stderr_with_error_prefix(self, capsys) -> None:
        """err() writes to stderr with 'docker: Error:' prefix."""
        docker.err("something broke")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "docker: Error: something broke\n"

    def test_msg_does_not_write_to_stdout(self, capsys) -> None:
        """msg() never writes to stdout."""
        docker.msg("test message")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_err_does_not_write_to_stdout(self, capsys) -> None:
        """err() never writes to stdout."""
        docker.err("test error")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestAuthDirectoryOverride:
    """Unit tests for SUITEWRIGHT_AUTH_DIR environment variable override."""

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_uses_env_var_for_auth_dir(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
    ) -> None:
        """cmd_test --live uses SUITEWRIGHT_AUTH_DIR env var as auth directory."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        custom_auth = tmp_path / "custom-auth"
        custom_auth.mkdir()

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": str(custom_auth)}),
            patch.object(Path, "is_file", return_value=True),
        ):
            docker.cmd_test(["--live"])

        cmd = mock_run.call_args[0][0]
        # The custom auth path should appear in a volume mount
        volume_args = []
        for i, arg in enumerate(cmd):
            if arg == "-v" and i + 1 < len(cmd):
                volume_args.append(cmd[i + 1])
        auth_mounts = [v for v in volume_args if "/app/suitewright-auth" in v]
        assert len(auth_mounts) == 1
        assert str(custom_auth.resolve()) in auth_mounts[0]

    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_uses_default_auth_dir_when_env_not_set(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        tmp_path,
    ) -> None:
        """cmd_test --live uses default ../suitewright-auth when env var not set."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "is_file", return_value=True),
        ):
            # Remove SUITEWRIGHT_AUTH_DIR if it exists
            os.environ.pop("SUITEWRIGHT_AUTH_DIR", None)
            docker.cmd_test(["--live"])

        cmd = mock_run.call_args[0][0]
        volume_args = []
        for i, arg in enumerate(cmd):
            if arg == "-v" and i + 1 < len(cmd):
                volume_args.append(cmd[i + 1])
        auth_mounts = [v for v in volume_args if "/app/suitewright-auth" in v]
        assert len(auth_mounts) == 1
        # Should contain the resolved default path
        assert "suitewright-auth" in auth_mounts[0]


# =============================================================================
# Property-Based Test: Message Formatting (Property 4)
# =============================================================================


class TestMessageFormattingProperty:
    """Property 4: Message formatting.

    For any message emitted by the script (status or error), the message SHALL
    be written to stderr (never stdout) and SHALL be prefixed with `docker: `.

    **Validates: Requirements 4.4, 4.5**

    Feature: docker-dev-workflow, Property 4: Message formatting
    """

    @given(
        text=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Z"),
                blacklist_characters="\x00",
            ),
            min_size=0,
            max_size=200,
        )
    )
    @settings(max_examples=100)
    def test_msg_always_outputs_prefixed_to_stderr(self, text: str) -> None:
        """msg(text) always outputs 'docker: {text}\\n' to stderr for any text.

        Feature: docker-dev-workflow, Property 4: Message formatting
        """
        fake_stderr = io.StringIO()
        fake_stdout = io.StringIO()
        with patch("sys.stderr", fake_stderr), patch("sys.stdout", fake_stdout):
            docker.msg(text)
        assert fake_stderr.getvalue() == f"docker: {text}\n"
        assert fake_stdout.getvalue() == ""

    @given(
        text=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Z"),
                blacklist_characters="\x00",
            ),
            min_size=0,
            max_size=200,
        )
    )
    @settings(max_examples=100)
    def test_err_always_outputs_error_prefixed_to_stderr(self, text: str) -> None:
        """err(text) always outputs 'docker: Error: {text}\\n' to stderr for any text.

        Feature: docker-dev-workflow, Property 4: Message formatting
        """
        fake_stderr = io.StringIO()
        fake_stdout = io.StringIO()
        with patch("sys.stderr", fake_stderr), patch("sys.stdout", fake_stdout):
            docker.err(text)
        assert fake_stderr.getvalue() == f"docker: Error: {text}\n"
        assert fake_stdout.getvalue() == ""

    @given(
        text=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Z"),
                blacklist_characters="\x00",
            ),
            min_size=0,
            max_size=200,
        )
    )
    @settings(max_examples=100)
    def test_msg_never_writes_to_stdout(self, text: str) -> None:
        """msg(text) never writes anything to stdout for any text.

        Feature: docker-dev-workflow, Property 4: Message formatting
        """
        fake_stderr = io.StringIO()
        fake_stdout = io.StringIO()
        with patch("sys.stderr", fake_stderr), patch("sys.stdout", fake_stdout):
            docker.msg(text)
        assert fake_stdout.getvalue() == ""

    @given(
        text=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Z"),
                blacklist_characters="\x00",
            ),
            min_size=0,
            max_size=200,
        )
    )
    @settings(max_examples=100)
    def test_err_never_writes_to_stdout(self, text: str) -> None:
        """err(text) never writes anything to stdout for any text.

        Feature: docker-dev-workflow, Property 4: Message formatting
        """
        fake_stderr = io.StringIO()
        fake_stdout = io.StringIO()
        with patch("sys.stderr", fake_stderr), patch("sys.stdout", fake_stdout):
            docker.err(text)
        assert fake_stdout.getvalue() == ""


class TestAuthDirectoryOverrideProperty:
    """Property 5: Auth directory override.

    For any valid directory path set in the SUITEWRIGHT_AUTH_DIR environment
    variable, the `test --live` mode SHALL use that path as the auth directory
    volume source in the Docker run command instead of the default
    `../suitewright-auth`.

    **Validates: Requirements 5.1, 5.2**

    Feature: docker-dev-workflow, Property 5: Auth directory override
    """

    # Strategy: generate path-like strings using valid path characters
    # Paths start with / and contain alphanumeric chars, hyphens, underscores, dots
    _path_segment = st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            whitelist_characters="-_.",
        ),
        min_size=1,
        max_size=20,
    ).filter(lambda s: s not in (".", "..") and not s.startswith("."))

    _path_strategy = st.builds(
        lambda segments: "/" + "/".join(segments),
        st.lists(_path_segment, min_size=1, max_size=5),
    )

    @given(auth_path=_path_strategy)
    @settings(max_examples=100)
    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_env_var_overrides_auth_dir_in_volume_mount(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        auth_path: str,
    ) -> None:
        """For any valid path set in SUITEWRIGHT_AUTH_DIR, that resolved path
        appears in the docker volume mount command for /app/suitewright-auth.

        Feature: docker-dev-workflow, Property 5: Auth directory override
        """
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        with (
            patch.dict(os.environ, {"SUITEWRIGHT_AUTH_DIR": auth_path}),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "is_file", return_value=True),
        ):
            docker.cmd_test(["--live"])

        cmd = mock_run.call_args[0][0]
        # Collect volume mount arguments
        volume_args = []
        for i, arg in enumerate(cmd):
            if arg == "-v" and i + 1 < len(cmd):
                volume_args.append(cmd[i + 1])

        # Find the auth volume mount (maps to /app/suitewright-auth:ro)
        auth_mounts = [v for v in volume_args if "/app/suitewright-auth:ro" in v]
        assert len(auth_mounts) == 1

        # The resolved path from the env var should be the source of the mount
        resolved_path = str(Path(auth_path).resolve())
        assert auth_mounts[0].startswith(resolved_path + ":")

    @given(auth_path=_path_strategy)
    @settings(max_examples=100)
    @patch("docker.run_preflight")
    @patch("docker.check_image")
    @patch("docker.check_docker")
    @patch("docker.subprocess.run")
    def test_default_auth_dir_used_when_env_not_set(
        self,
        mock_run: MagicMock,
        mock_check_docker: MagicMock,
        mock_check_image: MagicMock,
        mock_preflight: MagicMock,
        auth_path: str,
    ) -> None:
        """When SUITEWRIGHT_AUTH_DIR is NOT set, the default path containing
        'suitewright-auth' is used as the volume mount source.

        Feature: docker-dev-workflow, Property 5: Auth directory override
        """
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        # Ensure SUITEWRIGHT_AUTH_DIR is not set
        env_copy = os.environ.copy()
        env_copy.pop("SUITEWRIGHT_AUTH_DIR", None)

        with (
            patch.dict(os.environ, env_copy, clear=True),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "is_file", return_value=True),
        ):
            docker.cmd_test(["--live"])

        cmd = mock_run.call_args[0][0]
        # Collect volume mount arguments
        volume_args = []
        for i, arg in enumerate(cmd):
            if arg == "-v" and i + 1 < len(cmd):
                volume_args.append(cmd[i + 1])

        # Find the auth volume mount
        auth_mounts = [v for v in volume_args if "/app/suitewright-auth:ro" in v]
        assert len(auth_mounts) == 1

        # The default path should contain "suitewright-auth" in the source
        mount_source = auth_mounts[0].split(":/app/suitewright-auth:ro")[0]
        assert "suitewright-auth" in mount_source
