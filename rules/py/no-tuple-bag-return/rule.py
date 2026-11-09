"""Custom AST rule: `py/no-tuple-bag-return` (`PY002`)."""

from __future__ import annotations

import ast
from pathlib import Path


def _tuple_return_arity(returns: ast.expr | None) -> int:
    if not isinstance(returns, ast.Subscript):
        return 0
    val = returns.value
    is_tuple = (isinstance(val, ast.Name) and val.id in {"tuple", "Tuple"}) or (
        isinstance(val, ast.Attribute) and val.attr in {"tuple", "Tuple"}
    )
    if not is_tuple:
        return 0
    slc = returns.slice
    if isinstance(slc, ast.Tuple):
        if (
            len(slc.elts) == 2
            and isinstance(slc.elts[1], ast.Constant)
            and slc.elts[1].value is Ellipsis
        ):
            return 0
        return len(slc.elts)
    return 1


def check(tree: ast.AST, _path: Path) -> list[tuple[int, int, str]]:
    violations: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arity = _tuple_return_arity(node.returns)
            if arity >= 3 and node.returns is not None:
                violations.append(
                    (
                        node.returns.lineno,
                        node.returns.col_offset + 1,
                        f"`{node.name}` returns a {arity}-element tuple bag. "
                        "Fix: return a named `@dataclass` or `pydantic.BaseModel` instead of positional unpacking. Docs: `lints explain py/no-tuple-bag-return`.",
                    )
                )
    return violations
