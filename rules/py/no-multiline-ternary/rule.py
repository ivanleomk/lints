"""Custom AST rule: `py/no-multiline-ternary` (`PY003`)."""

from __future__ import annotations

import ast
from pathlib import Path


def check(tree: ast.AST, _path: Path) -> list[tuple[int, int, str]]:
    return [
        (
            node.lineno,
            node.col_offset + 1,
            "Multi-line `a if cond else b` expressions are banned. "
            "Fix: rewrite as an explicit `if / else` statement. Docs: `lints explain py/no-multiline-ternary`.",
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.IfExp)
        and node.end_lineno is not None
        and node.lineno != node.end_lineno
    ]
