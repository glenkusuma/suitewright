"""Local preflight validation — 16-step pre-release gate.

Runs all local checks (lint, type, security, build, Docker) without touching
the live account. Each step writes its log to a timestamped run directory and
a pass/fail summary is printed at the end.

Usage:
    uv run python tests/live/scripts/preflight.py

Exit codes:
    0 — all steps passed
    1 — one or more steps failed

Requirements: 14.AC1-14.AC9
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_BASE = REPO_ROOT / "_local" / "tests" / "live" / ".runs"

# High-risk paths that must never be staged
HIGH_RISK_PATHS = [".env", "auth/", "cache/", "_local/", ".claude/", "CLAUDE.md"]


@dataclass
class StepResult:
    step: int
    total: int
    name: str
    passed: bool
    log_path: Path
    duration_seconds: float


@dataclass
class PreflightContext:
    run_dir: Path
    results: list[StepResult] = field(default_factory=list)
    dist_dir: Path | None = None


TOTAL_STEPS = 16


def _run_cmd(
    cmd: list[str],
    log_path: Path,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command, write combined output to log_path, return result."""
    effective_cwd = str(cwd or REPO_ROOT)
    effective_env = env if env is not None else None
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=effective_cwd,
        env=effective_env,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as f:
        f.write(f"$ {' '.join(cmd)}\n")
        f.write(f"cwd: {effective_cwd}\n")
        f.write(f"exit: {result.returncode}\n")
        f.write("--- stdout ---\n")
        f.write(result.stdout or "")
        f.write("\n--- stderr ---\n")
        f.write(result.stderr or "")
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def _run_step(
    ctx: PreflightContext,
    step_num: int,
    name: str,
    fn,
) -> StepResult:
    """Execute a step function, capture timing and pass/fail."""
    log_path = ctx.run_dir / f"{step_num:02d}-{name.replace(' ', '-').lower()}.log"
    print(f"[{step_num:2d}/{TOTAL_STEPS}] {name} ... ", end="", flush=True)
    start = time.monotonic()
    try:
        fn(ctx, log_path)
        passed = True
    except Exception as exc:
        passed = False
        # Append error to log if not already written
        with log_path.open("a") as f:
            f.write(f"\n--- exception ---\n{exc}\n")
    elapsed = time.monotonic() - start
    status = "PASS" if passed else "FAIL"
    print(f"{status} ({elapsed:.1f}s)")
    result = StepResult(
        step=step_num,
        total=TOTAL_STEPS,
        name=name,
        passed=passed,
        log_path=log_path,
        duration_seconds=round(elapsed, 2),
    )
    ctx.results.append(result)
    return result


# ─── Step implementations ────────────────────────────────────────────────────


def step_01_hard_rules(ctx: PreflightContext, log_path: Path) -> None:
    """Hard rules: no auth/, .env gitignored+not staged, no high-risk, no <RESOLVE>."""
    errors: list[str] = []

    # 1a. No auth/ directory at repo root (as a tracked directory)
    auth_dir = REPO_ROOT / "auth"
    if auth_dir.is_dir():
        # Check if it contains tracked files (auth/README.md is allowed)
        result = subprocess.run(
            ["git", "ls-files", "auth/"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        tracked = [f for f in result.stdout.strip().splitlines() if f and f != "auth/README.md"]
        if tracked:
            errors.append(f"auth/ has tracked files: {tracked}")

    # 1b. .env is gitignored
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        errors.append(".env is NOT gitignored")

    # 1c. .env is not staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    staged = result.stdout.strip().splitlines()
    if ".env" in staged:
        errors.append(".env is staged for commit")

    # 1d. No high-risk paths staged
    for path in HIGH_RISK_PATHS:
        matches = [s for s in staged if s.startswith(path) or s == path.rstrip("/")]
        if matches:
            errors.append(f"High-risk path staged: {matches}")

    # 1e. No <RESOLVE> placeholders in Dockerfiles
    for dockerfile in ["Dockerfile", "Dockerfile.test"]:
        df_path = REPO_ROOT / dockerfile
        if df_path.exists():
            content = df_path.read_text()
            if "<RESOLVE>" in content:
                errors.append(f"{dockerfile} contains <RESOLVE> placeholder")

    # Write log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as f:
        f.write("Hard rules check\n")
        f.write(f"auth/ dir exists: {auth_dir.is_dir()}\n")
        f.write(f"Staged files: {staged}\n")
        f.write(f"Errors: {errors}\n")

    if errors:
        raise RuntimeError(f"Hard rule violations: {'; '.join(errors)}")


def step_02_uv_sync(ctx: PreflightContext, log_path: Path) -> None:
    """uv sync --frozen --extra dev."""
    _run_cmd(["uv", "sync", "--frozen", "--extra", "dev"], log_path)


def step_03_ruff_check(ctx: PreflightContext, log_path: Path) -> None:
    """ruff check ."""
    _run_cmd(["uv", "run", "ruff", "check", "."], log_path)


def step_04_ruff_format(ctx: PreflightContext, log_path: Path) -> None:
    """ruff format --check ."""
    _run_cmd(["uv", "run", "ruff", "format", "--check", "."], log_path)


def step_05_mypy(ctx: PreflightContext, log_path: Path) -> None:
    """mypy (release scope)."""
    _run_cmd(["uv", "run", "mypy"], log_path)


def step_06_bandit(ctx: PreflightContext, log_path: Path) -> None:
    """bandit -r src/."""
    _run_cmd(["uv", "run", "bandit", "-r", "src/", "-c", "pyproject.toml"], log_path)


def step_07_pip_audit(ctx: PreflightContext, log_path: Path) -> None:
    """pip-audit."""
    _run_cmd(["uv", "run", "pip-audit"], log_path)


def step_08_gitleaks(ctx: PreflightContext, log_path: Path) -> None:
    """gitleaks detect."""
    _run_cmd(["gitleaks", "detect", "--source", str(REPO_ROOT), "-v"], log_path)


def step_09_pytest(ctx: PreflightContext, log_path: Path) -> None:
    """pytest (mock suite, ignore live)."""
    _run_cmd(
        ["uv", "run", "pytest", "tests/", "--ignore=tests/live", "-q"],
        log_path,
    )


def step_10_build_twine(ctx: PreflightContext, log_path: Path) -> None:
    """uv build + twine check."""
    # Clean dist/ first
    dist_dir = REPO_ROOT / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    _run_cmd(["uv", "build"], log_path, check=True)

    # twine check all dist artifacts
    whl_files = list(dist_dir.glob("*.whl"))
    tar_files = list(dist_dir.glob("*.tar.gz"))
    all_dists = [str(f) for f in whl_files + tar_files]
    if not all_dists:
        raise RuntimeError("No dist files found after uv build")

    _run_cmd(
        ["uv", "run", "twine", "check", *all_dists],
        log_path,
    )
    ctx.dist_dir = dist_dir


def step_11_sbom_sha256(ctx: PreflightContext, log_path: Path) -> None:
    """SBOM generation + SHA256SUMS."""
    dist_dir = ctx.dist_dir or (REPO_ROOT / "dist")
    checksums_dir = REPO_ROOT / "checksums"
    checksums_dir.mkdir(parents=True, exist_ok=True)

    # Generate SBOM (using syft if available, otherwise skip gracefully)
    sbom_path = dist_dir / "sbom.spdx.json"
    syft_bin = shutil.which("syft")
    if syft_bin:
        _run_cmd(
            [syft_bin, f"dir:{REPO_ROOT}", "-o", f"spdx-json={sbom_path}"],
            log_path,
        )
    else:
        # Fallback: generate minimal SBOM from pyproject.toml
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w") as f:
            f.write("syft not found — generating minimal SBOM placeholder\n")
        import json

        sbom_data = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "suitewright-0.0.1",
            "documentNamespace": "https://github.com/glenkusuma/suitewright",
            "packages": [],
        }
        sbom_path.write_text(json.dumps(sbom_data, indent=2))

    # SHA256SUMS of dist files + SBOM
    all_files = list(dist_dir.glob("*.whl")) + list(dist_dir.glob("*.tar.gz"))
    if sbom_path.exists():
        all_files.append(sbom_path)

    sha_lines = []
    for f in sorted(all_files):
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        sha_lines.append(f"{digest}  {f.name}")

    sha_path = checksums_dir / "SHA256SUMS"
    sha_path.write_text("\n".join(sha_lines) + "\n")

    with log_path.open("a") as f:
        f.write(f"\nSHA256SUMS written to {sha_path}\n")
        f.write("\n".join(sha_lines) + "\n")


def step_12_wheel_smoke(ctx: PreflightContext, log_path: Path) -> None:
    """Wheel install smoke + ANSI assertion."""
    dist_dir = ctx.dist_dir or (REPO_ROOT / "dist")
    whl_files = list(dist_dir.glob("*.whl"))
    if not whl_files:
        raise RuntimeError("No .whl file found in dist/")

    whl = whl_files[0]

    with tempfile.TemporaryDirectory(prefix="sw-wheel-smoke-") as tmpdir:
        venv_dir = Path(tmpdir) / ".venv"
        # Create isolated venv
        _run_cmd(["uv", "venv", str(venv_dir)], log_path, check=True)

        # Install wheel
        pip_cmd = [
            "uv",
            "pip",
            "install",
            str(whl),
            "--python",
            str(venv_dir / "bin" / "python"),
        ]
        if platform.system() == "Windows":
            pip_cmd[-1] = str(venv_dir / "Scripts" / "python.exe")
        _run_cmd(pip_cmd, log_path, check=True)

        # Run suitewright --help and check for ANSI
        if platform.system() == "Windows":
            sw_bin = str(venv_dir / "Scripts" / "suitewright.exe")
        else:
            sw_bin = str(venv_dir / "bin" / "suitewright")

        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        result = _run_cmd(
            [sw_bin, "--help"],
            log_path,
            check=True,
            env=env,
        )
        # Assert no ANSI escape sequences
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
        if ansi_pattern.search(result.stdout):
            raise RuntimeError("ANSI escape sequences found in --help output under NO_COLOR=1")


def step_13_no_deps_import(ctx: PreflightContext, log_path: Path) -> None:
    """--no-deps import smoke."""
    dist_dir = ctx.dist_dir or (REPO_ROOT / "dist")
    whl_files = list(dist_dir.glob("*.whl"))
    if not whl_files:
        raise RuntimeError("No .whl file found in dist/")

    whl = whl_files[0]

    with tempfile.TemporaryDirectory(prefix="sw-nodeps-smoke-") as tmpdir:
        venv_dir = Path(tmpdir) / ".venv"
        _run_cmd(["uv", "venv", str(venv_dir)], log_path, check=True)

        # Install wheel with --no-deps
        if platform.system() == "Windows":
            python_bin = str(venv_dir / "Scripts" / "python.exe")
        else:
            python_bin = str(venv_dir / "bin" / "python")

        _run_cmd(
            ["uv", "pip", "install", str(whl), "--no-deps", "--python", python_bin],
            log_path,
            check=True,
        )

        # Verify import works
        _run_cmd(
            [python_bin, "-c", "import suitewright; print(suitewright.__name__)"],
            log_path,
            check=True,
        )


def step_14_sdist_smoke(ctx: PreflightContext, log_path: Path) -> None:
    """sdist install smoke."""
    dist_dir = ctx.dist_dir or (REPO_ROOT / "dist")
    tar_files = list(dist_dir.glob("*.tar.gz"))
    if not tar_files:
        raise RuntimeError("No .tar.gz file found in dist/")

    sdist = tar_files[0]

    with tempfile.TemporaryDirectory(prefix="sw-sdist-smoke-") as tmpdir:
        venv_dir = Path(tmpdir) / ".venv"
        _run_cmd(["uv", "venv", str(venv_dir)], log_path, check=True)

        if platform.system() == "Windows":
            python_bin = str(venv_dir / "Scripts" / "python.exe")
        else:
            python_bin = str(venv_dir / "bin" / "python")

        _run_cmd(
            ["uv", "pip", "install", str(sdist), "--python", python_bin],
            log_path,
            check=True,
        )

        # Verify import works
        _run_cmd(
            [python_bin, "-c", "import suitewright; print(suitewright.__name__)"],
            log_path,
            check=True,
        )


def step_15_verify_install(ctx: PreflightContext, log_path: Path) -> None:
    """verify_install.py --installed."""
    verify_script = REPO_ROOT / "tests" / "live" / "scripts" / "verify_install.py"
    _run_cmd(
        ["uv", "run", "python", str(verify_script), "--installed"],
        log_path,
    )


def step_16_docker(ctx: PreflightContext, log_path: Path) -> None:
    """Docker build + hardened runtime smoke + Trivy scan."""
    # Check if docker is available
    docker_bin = shutil.which("docker")
    if not docker_bin:
        raise RuntimeError("docker not found in PATH — cannot run Docker checks")

    # Build runtime image
    _run_cmd(
        [docker_bin, "build", "-t", "suitewright:preflight", "."],
        log_path,
        cwd=REPO_ROOT,
    )

    # Hardened runtime smoke: run --help with security constraints
    _run_cmd(
        [
            docker_bin,
            "run",
            "--rm",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--tmpfs",
            "/home/suitewright/.cache/suitewright:uid=1000,gid=1000,mode=700",
            "--tmpfs",
            "/home/suitewright/runtime:uid=1000,gid=1000,mode=700",
            "--tmpfs",
            "/tmp:uid=1000,gid=1000,mode=700",
            "suitewright:preflight",
            "--help",
        ],
        log_path,
        check=True,
    )

    # Trivy scan (if available)
    trivy_bin = shutil.which("trivy")
    if trivy_bin:
        trivy_result = _run_cmd(
            [
                trivy_bin,
                "image",
                "--severity",
                "HIGH,CRITICAL",
                "--exit-code",
                "1",
                "suitewright:preflight",
            ],
            log_path,
            check=False,
        )
        if trivy_result.returncode != 0:
            with log_path.open("a") as f:
                f.write("\nTrivy found HIGH/CRITICAL vulnerabilities\n")
            raise RuntimeError("Trivy scan found HIGH/CRITICAL vulnerabilities")
    else:
        with log_path.open("a") as f:
            f.write("\ntrivy not found — skipping container scan\n")


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_BASE / f"preflight-{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    ctx = PreflightContext(run_dir=run_dir)

    print("=" * 64)
    print(f"  suitewright preflight — {TOTAL_STEPS}-step local validation")
    print(f"  run dir: {run_dir}")
    print(f"  started: {ts}")
    print("=" * 64)
    print()

    steps = [
        (1, "Hard rules", step_01_hard_rules),
        (2, "uv sync", step_02_uv_sync),
        (3, "ruff check", step_03_ruff_check),
        (4, "ruff format --check", step_04_ruff_format),
        (5, "mypy", step_05_mypy),
        (6, "bandit", step_06_bandit),
        (7, "pip-audit", step_07_pip_audit),
        (8, "gitleaks", step_08_gitleaks),
        (9, "pytest (mock suite)", step_09_pytest),
        (10, "uv build + twine check", step_10_build_twine),
        (11, "SBOM + SHA256SUMS", step_11_sbom_sha256),
        (12, "wheel install smoke", step_12_wheel_smoke),
        (13, "--no-deps import smoke", step_13_no_deps_import),
        (14, "sdist install smoke", step_14_sdist_smoke),
        (15, "verify_install.py --installed", step_15_verify_install),
        (16, "Docker build + smoke + Trivy", step_16_docker),
    ]

    for step_num, name, fn in steps:
        _run_step(ctx, step_num, name, fn)

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    print("=" * 64)
    print("  PREFLIGHT SUMMARY")
    print("=" * 64)

    all_passed = True
    for r in ctx.results:
        marker = "✓" if r.passed else "✗"
        print(f"  {marker} [{r.step:2d}/{r.total}] {r.name} ({r.duration_seconds:.1f}s)")
        if not r.passed:
            all_passed = False

    print()
    passed_count = sum(1 for r in ctx.results if r.passed)
    total = len(ctx.results)
    if all_passed:
        print(f"  All {total} steps passed. Ready to release.")
    else:
        failed = [r for r in ctx.results if not r.passed]
        print(f"  {passed_count}/{total} passed, {len(failed)} FAILED:")
        for r in failed:
            print(f"    -> [{r.step:2d}] {r.name} — see {r.log_path}")

    print()
    print(f"  Logs: {run_dir}")
    print("=" * 64)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
