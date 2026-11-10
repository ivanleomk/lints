"""Custom AST rule: `py/no-raw-os-environ` (`PY004`)."""

from __future__ import annotations

import ast
from pathlib import Path

from pydantic import BaseModel, Field

ROOT_MARKERS = (".git", "pyproject.toml")


class _BoundaryConfig(BaseModel):
    allowed_dirs: frozenset[str] = Field(alias="allowedDirs")
    allowed_files: frozenset[str] = Field(alias="allowedFiles")


_CONFIG = _BoundaryConfig.model_validate_json(Path(__file__).with_name("rule.json").read_text())


def _find_project_root(path: Path) -> Path | None:
    for parent in path.parents:
        if any((parent / marker).exists() for marker in ROOT_MARKERS):
            return parent
    return None


def _project_dir_parts(path: Path) -> tuple[str, ...]:
    if not path.is_absolute() and not path.exists():
        return path.parts[:-1]
    resolved = path.resolve()
    root = _find_project_root(resolved)
    if root is not None:
        return resolved.relative_to(root).parts[:-1]
    if not path.is_absolute():
        return path.parts[:-1]
    if resolved.parent != resolved:
        return (resolved.parent.name,)
    return ()


def _is_boundary_file(path: Path) -> bool:
    if path.name in _CONFIG.allowed_files or path.name.startswith("test_"):
        return True
    return any(part in _CONFIG.allowed_dirs for part in _project_dir_parts(path))


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
