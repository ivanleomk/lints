"""End-to-end verification for Stop hook untracked directories and NUL-safe git paths."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from lints.cli import _dirty_code_files

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_LINTS = REPO_ROOT / "bin" / "lints"
BAD_PY = 'x = object()\ngetattr(x, "a", None)\n'
CLEAN_PY = "x = 1\n"
BAD_TS = "export const bad: any = 1;\n"
CLEAN_TS = "export const clean = 1;\n"


def _init_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)


def _run_stop_hook(repo: Path) -> dict[str, str]:
    payload = json.dumps(
        {
            "terminationReason": "NO_TOOL_CALL",
            "workspacePaths": [str(repo)],
        }
    )
    res = subprocess.run(
        [str(BIN_LINTS), "hook", "stop", "--agent", "antigravity"],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(res.stdout)


@pytest.mark.parametrize(
    ("rel_path", "source", "expected_decision", "expected_snippet"),
    [
        ("new_pkg/bad.py", BAD_PY, "continue", "no-getattr"),
        ("deep/nested/pkg/bad.py", BAD_PY, "continue", "no-getattr"),
        ('dir with spaces/bad "quote" file.py', BAD_PY, "continue", "no-getattr"),
        ('ts space/bad "quote".ts', BAD_TS, "continue", "no-explicit-any"),
        ("new_pkg/clean.py", CLEAN_PY, "allow", ""),
        ('ts space/clean "quote".ts', CLEAN_TS, "allow", ""),
    ],
)
def test_stop_hook_untracked_dirs_and_special_filenames(
    tmp_path: Path,
    rel_path: str,
    source: str,
    expected_decision: str,
    expected_snippet: str,
) -> None:
    repo = tmp_path / "ws"
    _init_git_repo(repo)

    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)

    result = _run_stop_hook(repo)
    assert result["decision"] == expected_decision
    if expected_snippet:
        assert expected_snippet in result["reason"]


def test_stop_hook_handles_renamed_files_with_spaces_and_quotes(tmp_path: Path) -> None:
    repo = tmp_path / "ws"
    _init_git_repo(repo)

    orig = repo / "orig_module.py"
    orig.write_text(CLEAN_PY)
    subprocess.run(["git", "add", "orig_module.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)

    dest_rel = 'renamed dir/new "quoted" module.py'
    dest = repo / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "mv", "orig_module.py", dest_rel], cwd=repo, check=True)
    dest.write_text(BAD_PY)

    assert _dirty_code_files([str(repo)]) == [str(dest.resolve())]

    result = _run_stop_hook(repo)
    assert result["decision"] == "continue"
    assert "no-getattr" in result["reason"]


@pytest.mark.parametrize(
    ("rel_path", "bad_source", "clean_source", "expected_snippet"),
    [
        ('pkg space/staged "quote".py', BAD_PY, CLEAN_PY, "no-getattr"),
        ('ui space/staged "quote".ts', BAD_TS, CLEAN_TS, "no-explicit-any"),
    ],
)
def test_pre_commit_hook_handles_nul_delimited_special_filenames(
    tmp_path: Path,
    rel_path: str,
    bad_source: str,
    clean_source: str,
    expected_snippet: str,
) -> None:
    repo = tmp_path / "ws"
    _init_git_repo(repo)

    subprocess.run(
        [str(BIN_LINTS), "hook", "install", "--agent", "git", "--local"],
        cwd=repo,
        check=True,
    )

    special_file = repo / rel_path
    special_file.parent.mkdir(parents=True, exist_ok=True)
    special_file.write_text(bad_source)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)

    blocked = subprocess.run(
        ["git", "commit", "-m", "should block"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode != 0
    assert expected_snippet in (blocked.stdout + blocked.stderr)

    special_file.write_text(clean_source)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    allowed = subprocess.run(
        ["git", "commit", "-m", "should allow"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert allowed.returncode == 0

    notes = repo / 'notes "doc".md'
    notes.write_text("# Docs\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    docs_commit = subprocess.run(
        ["git", "commit", "-m", "docs only"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert docs_commit.returncode == 0
