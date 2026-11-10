"""End-to-end tests for tokenized `# noqa` scoping in custom Python AST checks."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
LINTS_BIN = REPO_DIR / "bin" / "lints"


@pytest.mark.parametrize(
    ("case_id", "source"),
    [
        (
            "unrelated_ruff_code",
            'def read_attr(obj: object) -> object:\n    return getattr(obj, "x")  # noqa: B009\n',
        ),
        (
            "unrelated_custom_code",
            "def read_attr(obj: object, key: str) -> object:\n"
            "    return getattr(obj, key, None)  # noqa: PY005\n",
        ),
        (
            "string_literal_noqa",
            'def read_attr(obj: object) -> object:\n    return getattr(obj, "# noqa", None)\n',
        ),
        (
            "fstring_literal_noqa",
            "def read_attr(obj: object, p: str) -> object:\n"
            '    return getattr(obj, f"{p} # noqa: PY006", None)\n',
        ),
        (
            "prose_comment_mentioning_noqa",
            "def read_attr(obj: object, key: str) -> object:\n"
            "    return getattr(obj, key, None)  # avoid noqa comments here\n",
        ),
        (
            "empty_noqa_colon",
            "def read_attr(obj: object, key: str) -> object:\n"
            "    return getattr(obj, key, None)  # noqa:\n",
        ),
    ],
)
def test_non_matching_or_non_comment_noqa_still_reports_py006(
    tmp_path: Path, case_id: str, source: str
) -> None:
    target = tmp_path / f"{case_id}.py"
    target.write_text(source)

    res = subprocess.run(
        [str(LINTS_BIN), "lint", str(target)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = res.stdout + res.stderr

    assert res.returncode == 1
    assert "PY006 [py/no-getattr]" in combined


@pytest.mark.parametrize(
    ("case_id", "source"),
    [
        (
            "exact_custom_code",
            "def read_attr(obj: object, key: str) -> object:\n"
            "    return getattr(obj, key, None)  # noqa: PY006\n",
        ),
        (
            "exact_rule_id",
            "def read_attr(obj: object, key: str) -> object:\n"
            "    return getattr(obj, key, None)  # noqa: py/no-getattr\n",
        ),
        (
            "multi_code_ruff_and_custom",
            "def read_attr(obj: object) -> object:\n"
            '    return getattr(obj, "x")  # noqa: B009, PY006\n',
        ),
        (
            "nested_after_type_ignore",
            "def read_attr(obj: object, key: str) -> object:\n"
            "    return getattr(obj, key, None)  # type: ignore[misc]  # noqa: PY006\n",
        ),
        (
            "bare_noqa_blanket",
            'def read_attr(obj: object) -> object:\n    return getattr(obj, "x")  # noqa\n',
        ),
        (
            "bare_noqa_with_trailing_reason",
            "def read_attr(obj: object) -> object:\n"
            '    return getattr(obj, "x")  # noqa  # legacy boundary\n',
        ),
    ],
)
def test_matching_or_bare_noqa_suppresses_py006(tmp_path: Path, case_id: str, source: str) -> None:
    target = tmp_path / f"{case_id}.py"
    target.write_text(source)

    res = subprocess.run(
        [str(LINTS_BIN), "lint", str(target)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = res.stdout + res.stderr

    assert res.returncode == 0, combined
    assert "PY006" not in combined


def test_same_line_partial_suppression_keeps_unsuppressed_custom_rule(tmp_path: Path) -> None:
    target = tmp_path / "partial.py"
    target.write_text(
        "def probe(data: dict[str, dict[str, object]], key: str) -> object:\n"
        '    return getattr(data.get("a", {}).get("b"), key, None)  # noqa: PY005\n'
    )

    res = subprocess.run(
        [str(LINTS_BIN), "lint", str(target)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = res.stdout + res.stderr

    assert res.returncode == 1
    assert "PY005" not in combined
    assert "PY006 [py/no-getattr]" in combined


def test_lints_fix_preserves_custom_py_noqa_code(tmp_path: Path) -> None:
    target = tmp_path / "fixable.py"
    original = (
        "def read_attr(obj: object, key: str) -> object:\n"
        "    return getattr(obj, key, None)  # noqa: PY006\n"
    )
    target.write_text(original)

    res = subprocess.run(
        [str(LINTS_BIN), "fix", str(target)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 0, res.stdout + res.stderr
    assert target.read_text() == original
