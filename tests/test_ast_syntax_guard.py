"""End-to-end tests ensuring `_run_lint` guards `ast.parse` against `SyntaxError`."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
LINTS_BIN = REPO_DIR / "bin" / "lints"


@pytest.mark.parametrize("subcmd", ["lint", "fix"])
@pytest.mark.parametrize(
    ("case_id", "broken_source"),
    [
        ("incomplete_def", "def broken(:\n    pass\n"),
        ("missing_colon", "if True\n    value = 1\n"),
        ("unterminated_str", 'greeting = "hello\n'),
    ],
)
def test_syntax_error_exits_cleanly_without_traceback(
    tmp_path: Path, subcmd: str, case_id: str, broken_source: str
) -> None:
    bad_file = tmp_path / f"{case_id}.py"
    bad_file.write_text(broken_source)

    res = subprocess.run(
        [str(LINTS_BIN), subcmd, str(bad_file)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = res.stdout + res.stderr

    assert res.returncode == 1
    assert "invalid-syntax" in combined
    assert "Traceback (most recent call last)" not in combined
    assert "SyntaxError:" not in combined


def test_syntax_error_does_not_abort_custom_ast_checks_on_sibling_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "lints.toml").write_text("[py]\nno-chained-dict-get = true\n")
    broken_file = tmp_path / "a_broken.py"
    broken_file.write_text("def broken(:\n    pass\n")
    sibling_file = tmp_path / "b_sibling.py"
    sibling_file.write_text(
        "def read_nested(data: dict[str, dict[str, str]]) -> str | None:\n"
        '    return data.get("outer", {}).get("inner")\n'
    )

    res = subprocess.run(
        [str(LINTS_BIN), "lint", str(broken_file), str(sibling_file)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = res.stdout + res.stderr

    assert res.returncode == 1
    assert "invalid-syntax" in combined
    assert "[py/no-chained-dict-get]" in combined
    assert "Traceback (most recent call last)" not in combined
