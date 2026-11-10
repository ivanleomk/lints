"""End-to-end tests for mixed-language file arguments passed to `lints`."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
LINTS_BIN = str(REPO_DIR / "bin" / "lints")


@pytest.mark.parametrize(
    ("subcmd", "py_src", "expected_py"),
    [
        ("lint", 'label: str = "ok"\n', 'label: str = "ok"\n'),
        ("fix", "label: str = 'ok'\n", 'label: str = "ok"\n'),
    ],
)
def test_mixed_language_valid_files_succeed(
    tmp_path: Path, subcmd: str, py_src: str, expected_py: str
) -> None:
    py_file = tmp_path / "ok.py"
    ts_file = tmp_path / "ok.ts"
    py_file.write_text(py_src)
    ts_src = "export const y: number = 2;\n"
    ts_file.write_text(ts_src)

    res = subprocess.run(
        [LINTS_BIN, subcmd, str(py_file), str(ts_file)],
        capture_output=True,
        text=True,
        check=False,
    )

    combined = f"{res.stdout}\n{res.stderr}"
    assert res.returncode == 0, combined
    assert "invalid-syntax" not in combined
    assert py_file.read_text() == expected_py
    assert ts_file.read_text() == ts_src


@pytest.mark.parametrize(
    ("py_src", "ts_src", "expected_token"),
    [
        ("import os\n\nx: int = 1\n", "export const y: number = 2;\n", "F401"),
        ("x: int = 1\n", "export const y: any = 2;\n", "no-explicit-any"),
    ],
)
def test_mixed_language_violations_route_to_matching_linter(
    tmp_path: Path, py_src: str, ts_src: str, expected_token: str
) -> None:
    py_file = tmp_path / "sample.py"
    ts_file = tmp_path / "sample.ts"
    py_file.write_text(py_src)
    ts_file.write_text(ts_src)

    res = subprocess.run(
        [LINTS_BIN, "lint", str(py_file), str(ts_file)],
        capture_output=True,
        text=True,
        check=False,
    )

    combined = f"{res.stdout}\n{res.stderr}"
    assert res.returncode == 1
    assert expected_token in combined
    assert "invalid-syntax" not in combined


def test_stop_hook_allows_clean_mixed_language_edits(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    (tmp_path / "ok.py").write_text("x: int = 1\n")
    (tmp_path / "ok.ts").write_text("export const y: number = 2;\n")

    payload = json.dumps(
        {
            "terminationReason": "NO_TOOL_CALL",
            "workspacePaths": [str(tmp_path)],
        }
    )
    res = subprocess.run(
        [LINTS_BIN, "hook", "stop", "--agent", "antigravity"],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == {"decision": "allow"}
