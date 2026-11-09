"""Custom AST rule: `py/no-getattr` (`PY006`)."""

from __future__ import annotations

import ast
from pathlib import Path


def check(tree: ast.AST, _path: Path) -> list[tuple[int, int, str]]:
    return [
        (
            node.lineno,
            node.col_offset + 1,
            "Dynamic `getattr()` is banned. "
            "Fix: parse into a `pydantic.BaseModel` or type with a `Protocol` and access attributes directly. Docs: `lints explain py/no-getattr`.",
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
    ]
