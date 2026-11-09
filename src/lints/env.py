"""Environment boundary helpers for `lints`."""

from __future__ import annotations

import os
from pathlib import Path


def ensure_rich_path() -> str:
    home = str(Path.home())
    extra = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        f"{home}/.local/bin",
        f"{home}/.bun/bin",
        f"{home}/.cargo/bin",
    ]
    current = os.environ.get("PATH", "/usr/bin:/bin")
    merged = list(dict.fromkeys([*extra, *current.split(":")]))
    new_path = ":".join(part for part in merged if part)
    os.environ["PATH"] = new_path
    return new_path


def get_editor() -> str | None:
    visual = os.environ.get("VISUAL")
    if visual:
        return visual
    return os.environ.get("EDITOR")


def non_interactive_git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10")
    return env


def path_entries() -> list[str]:
    return os.environ.get("PATH", "").split(":")
