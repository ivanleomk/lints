"""End-to-end tests for `HookAction` CLI boundary validation in `lints hook`."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from lints.cli import HookAction

REPO_ROOT = Path(__file__).resolve().parent.parent
LINTS_BIN = str(REPO_ROOT / "bin/lints")


def _run_lints(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [LINTS_BIN, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_hook_action_enum_values() -> None:
    assert {a.value for a in HookAction} == {"install", "uninstall", "stop", "pre-invocation"}


@pytest.mark.parametrize(
    ("agent", "rel_cfg", "expected_install_prefix", "expected_uninstall_prefix"),
    [
        (
            "antigravity",
            ".agents/hooks.json",
            "Installed Antigravity hooks",
            "Uninstalled Antigravity hooks",
        ),
        (
            "claude",
            ".claude/settings.json",
            "Installed Claude Code hooks",
            "Uninstalled Claude Code hooks",
        ),
        ("codex", ".codex/hooks.json", "Installed Codex hooks", "Uninstalled Codex hooks"),
    ],
)
def test_json_agent_invalid_action_preserves_installed_hooks(
    tmp_path: Path,
    agent: str,
    rel_cfg: str,
    expected_install_prefix: str,
    expected_uninstall_prefix: str,
) -> None:
    install_res = _run_lints(tmp_path, "hook", "install", "--agent", agent, "--local")
    assert install_res.returncode == 0, install_res.stderr
    assert install_res.stdout.startswith(expected_install_prefix)

    cfg_path = tmp_path / rel_cfg
    before_bytes = cfg_path.read_text()
    assert LINTS_BIN in before_bytes

    bad_res = _run_lints(tmp_path, "hook", "status", "--agent", agent, "--local")
    assert bad_res.returncode != 0
    assert "status" in bad_res.stderr
    assert "Statused" not in bad_res.stdout
    assert cfg_path.read_text() == before_bytes

    uninstall_res = _run_lints(tmp_path, "hook", "uninstall", "--agent", agent, "--local")
    assert uninstall_res.returncode == 0, uninstall_res.stderr
    assert uninstall_res.stdout.startswith(expected_uninstall_prefix)
    assert LINTS_BIN not in json.dumps(json.loads(cfg_path.read_text()))


@pytest.mark.parametrize("bad_action", ["status", "enable"])
def test_git_invalid_action_does_not_link_pre_commit(tmp_path: Path, bad_action: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    pre_commit = tmp_path / ".git/hooks/pre-commit"

    bad_res = _run_lints(tmp_path, "hook", bad_action, "--agent", "git", "--local")
    assert bad_res.returncode != 0
    assert bad_action in bad_res.stderr
    assert not pre_commit.exists()
    assert not pre_commit.is_symlink()

    install_res = _run_lints(tmp_path, "hook", "install", "--agent", "git", "--local")
    assert install_res.returncode == 0, install_res.stderr
    assert pre_commit.is_symlink()

    uninstall_res = _run_lints(tmp_path, "hook", "uninstall", "--agent", "git", "--local")
    assert uninstall_res.returncode == 0, uninstall_res.stderr
    assert not pre_commit.exists()
    assert not pre_commit.is_symlink()
