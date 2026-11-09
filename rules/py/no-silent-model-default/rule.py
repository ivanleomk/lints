"""Custom AST rule: `py/no-silent-model-default` (`PY001`)."""

from __future__ import annotations

import ast
from pathlib import Path

MODEL_BASES = {"BaseModel", "SQLModel"}


def _is_model_or_dataclass(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in MODEL_BASES:
            return True
        if isinstance(base, ast.Attribute) and base.attr in MODEL_BASES:
            return True
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id == "dataclass":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "dataclass":
            return True
    return False


def check(tree: ast.AST, _path: Path) -> list[tuple[int, int, str]]:
    violations: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_model_or_dataclass(node):
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and isinstance(stmt.annotation, ast.Name)
                    and stmt.annotation.id == "str"
                    and isinstance(stmt.value, ast.Constant)
                    and stmt.value.value == ""
                ):
                    field = stmt.target.id
                    violations.append(
                        (
                            stmt.lineno,
                            stmt.col_offset + 1,
                            f'`{node.name}.{field}: str = ""` uses a silent empty-string default that masks missing data. '
                            f"Fix: require `{field}: str` or use `{field}: str | None = None`. Docs: `lints explain py/no-silent-model-default`.",
                        )
                    )
    return violations
