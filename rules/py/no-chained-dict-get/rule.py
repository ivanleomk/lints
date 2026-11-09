"""Custom AST rule: `py/no-chained-dict-get` (`PY005`)."""

from __future__ import annotations

import ast
from pathlib import Path


def check(tree: ast.AST, _path: Path) -> list[tuple[int, int, str]]:
    return [
        (
            node.lineno,
            node.col_offset + 1,
            "Chained `.get(...).get(...)` untyped dict probing is banned. "
            "Fix: parse the dictionary once at the boundary with `BaseModel.model_validate(...)` and access typed fields. Docs: `lints explain py/no-chained-dict-get`.",
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Attribute)
        and node.func.value.func.attr == "get"
    ]
