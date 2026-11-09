"""Custom AST rule: `py/no-raw-os-environ` (`PY004`)."""

from __future__ import annotations

import ast
from pathlib import Path

ALLOWED_FILENAMES = {"env.py", "config.py", "settings.py", "conftest.py", "cli.py"}
ALLOWED_DIRS = {"scripts", "tests", "test", "bin"}


def _is_boundary_file(path: Path) -> bool:
    if path.name in ALLOWED_FILENAMES or path.name.startswith("test_"):
        return True
    return any(part in ALLOWED_DIRS for part in path.parts)


def check(tree: ast.AST, path: Path) -> list[tuple[int, int, str]]:
    if _is_boundary_file(path):
        return []

    violations: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "environ"
        ):
            violations.append(
                (
                    node.lineno,
                    node.col_offset + 1,
                    "Raw `os.environ` access outside `env.py`/`settings.py` is banned. "
                    "Fix: validate environment variables once via `pydantic_settings.BaseSettings` in `env.py` or `settings.py`. Docs: `lints explain py/no-raw-os-environ`.",
                )
            )
        elif isinstance(node, ast.Call) and (
            (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "getenv"
            )
            or (isinstance(node.func, ast.Name) and node.func.id == "getenv")
        ):
            violations.append(
                (
                    node.lineno,
                    node.col_offset + 1,
                    "Raw `getenv()` access outside `env.py`/`settings.py` is banned. "
                    "Fix: validate environment variables once via `pydantic_settings.BaseSettings` in `env.py` or `settings.py`. Docs: `lints explain py/no-raw-os-environ`.",
                )
            )
    return violations
