"""End-to-end CLI tests for `py/no-raw-os-environ` (`PY004`) project-relative path checks."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
BIN_LINTS = REPO_DIR / "bin" / "lints"
RAW_ENVIRON_SNIPPET = 'import os\n\nx = os.getenv("SECRET")\n'


def _init_marker(project_dir: Path, marker: str | None) -> None:
    if marker == ".git":
        subprocess.run(["git", "init", "--quiet", str(project_dir)], check=True)
    elif marker == "pyproject.toml":
        (project_dir / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n')


@pytest.mark.parametrize(
    ("host_rel_project", "marker", "file_rel"),
    [
        ("test/demo_app", None, "worker.py"),
        ("test/my_app", ".git", "app/worker.py"),
        ("scripts/my_app", "pyproject.toml", "app/worker.py"),
        ("bin/my_app", "pyproject.toml", "service/worker.py"),
        ("workspace/test", "pyproject.toml", "app/worker.py"),
    ],
)
def test_host_parent_dirs_do_not_disable_py004(
    tmp_path: Path,
    host_rel_project: str,
    marker: str | None,
    file_rel: str,
) -> None:
    project_dir = tmp_path / host_rel_project
    target_file = project_dir / file_rel
    target_file.parent.mkdir(parents=True, exist_ok=True)
    _init_marker(project_dir, marker)
    target_file.write_text(RAW_ENVIRON_SNIPPET)

    res = subprocess.run(
        [str(BIN_LINTS), "lint", str(project_dir)],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 1, (
        f"Expected PY004 failure, got stdout={res.stdout!r} stderr={res.stderr!r}"
    )
    assert "PY004 [py/no-raw-os-environ]" in res.stdout
    assert str(target_file) in res.stdout


@pytest.mark.parametrize(
    ("marker", "exempt_rel"),
    [
        (".git", "tests/worker.py"),
        ("pyproject.toml", "tests/unit/worker.py"),
        ("pyproject.toml", "scripts/worker.py"),
        ("pyproject.toml", "bin/worker.py"),
        ("pyproject.toml", "app/env.py"),
    ],
)
def test_in_project_boundary_dirs_and_files_remain_exempted(
    tmp_path: Path,
    marker: str,
    exempt_rel: str,
) -> None:
    project_dir = tmp_path / "test" / "my_app"
    exempt_file = project_dir / exempt_rel
    exempt_file.parent.mkdir(parents=True, exist_ok=True)
    _init_marker(project_dir, marker)
    exempt_file.write_text(RAW_ENVIRON_SNIPPET)

    res = subprocess.run(
        [str(BIN_LINTS), "lint", str(project_dir)],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 0, (
        f"Expected exemption, got stdout={res.stdout!r} stderr={res.stderr!r}"
    )
    assert "PY004" not in res.stdout


def test_default_cwd_lint_inside_host_test_dir_flags_py004(tmp_path: Path) -> None:
    project_dir = tmp_path / "test" / "my_app"
    worker = project_dir / "app" / "worker.py"
    worker.parent.mkdir(parents=True, exist_ok=True)
    _init_marker(project_dir, "pyproject.toml")
    worker.write_text(RAW_ENVIRON_SNIPPET)

    res = subprocess.run(
        [str(BIN_LINTS), "lint"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 1
    assert "PY004 [py/no-raw-os-environ]" in res.stdout


def test_configured_ignore_folders_are_skipped(tmp_path: Path) -> None:
    project_dir = tmp_path / "app"
    for ignored in ("dist", "build", ".venv", "node_modules"):
        bad = project_dir / ignored / "worker.py"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text(RAW_ENVIRON_SNIPPET)
    clean = project_dir / "src" / "main.py"
    clean.parent.mkdir(parents=True, exist_ok=True)
    clean.write_text("X = 1\n")

    res = subprocess.run(
        [str(BIN_LINTS), "lint", str(project_dir)],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
