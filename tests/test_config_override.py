"""End-to-end CLI tests for --config overrides."""

from __future__ import annotations

from pathlib import Path
import subprocess

REPO_DIR = Path(__file__).resolve().parent.parent
BIN_LINTS = REPO_DIR / "bin" / "lints"
BAD_PY = (
    "def read_field(obj: object, field: str) -> object:\n"
    "    try:\n"
    "        return getattr(obj, field)\n"
    "    except Exception:\n"
    "        return None\n"
)


def _run_lints(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BIN_LINTS), *args], cwd=cwd or REPO_DIR, capture_output=True, text=True, check=False
    )


def test_config_flag_overrides_default_target_folder(tmp_path: Path) -> None:
    """Passing --config uses [lints].target relative to the custom config file."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "clean.py").write_text("X = 1\n")
    (tmp_path / "other.py").write_text(BAD_PY)

    custom_cfg = tmp_path / "custom.toml"
    custom_cfg.write_text('[lints]\ntarget = "src"\n')

    res = _run_lints("lint", "--config", str(custom_cfg), cwd=tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr


def test_config_flag_disables_py_ruff_and_ast_rules(tmp_path: Path) -> None:
    """Passing --config compiles a temporary Ruff config and filters Python AST rules."""
    app_py = tmp_path / "app.py"
    app_py.write_text(BAD_PY)

    fail_res = _run_lints("lint", str(app_py))
    assert fail_res.returncode == 1
    assert "BLE001" in fail_res.stdout
    assert "PY006" in fail_res.stdout

    custom_cfg = tmp_path / "custom.toml"
    custom_cfg.write_text("[py]\nno-blind-except = false\nno-getattr = false\n")
    pass_res = _run_lints("lint", "--config", str(custom_cfg), str(app_py))
    assert pass_res.returncode == 0, pass_res.stdout + pass_res.stderr


def test_config_flag_disables_ts_config_and_ast_plugin_rules(tmp_path: Path) -> None:
    """Passing --config compiles temporary Oxlint config + TS AST plugin bundle."""
    widget_ts = tmp_path / "widget.ts"
    widget_ts.write_text(
        "export const pick = (flag: boolean): number =>\n  flag\n    ? 1\n    : 2;\nexport default pick;\n"
    )
    fail_res = _run_lints("lint", str(widget_ts))
    assert fail_res.returncode == 1
    assert "no-default-export" in fail_res.stdout
    assert "no-multiline-ternary" in fail_res.stdout

    custom_cfg = tmp_path / "custom.toml"
    custom_cfg.write_text("[ts]\nno-default-export = false\nno-multiline-ternary = false\n")
    pass_res = _run_lints("lint", "-c", str(custom_cfg), str(widget_ts))
    assert pass_res.returncode == 0, pass_res.stdout + pass_res.stderr


def test_enable_disable_target_and_list_with_config_flag(tmp_path: Path) -> None:
    """enable, disable, target, and list operate on --config without touching central config.toml."""
    central_before = (REPO_DIR / "config.toml").read_text()
    custom_cfg = tmp_path / "project.toml"

    assert _run_lints("target", "src", "--config", str(custom_cfg)).returncode == 0
    assert _run_lints("target", "--config", str(custom_cfg)).stdout.strip() == "src"
    assert (
        _run_lints("disable", "ts/no-default-export", "--config", str(custom_cfg)).returncode == 0
    )
    res_list = _run_lints("list", "--config", str(custom_cfg))
    assert "target = 'src'" in res_list.stdout
    assert "[off] ts/no-default-export" in res_list.stdout
    assert _run_lints("enable", "ts/no-default-export", "--config", str(custom_cfg)).returncode == 0
    assert "[on ] ts/no-default-export" in _run_lints("list", "--config", str(custom_cfg)).stdout
    assert (REPO_DIR / "config.toml").read_text() == central_before


def test_git_repo_root_lints_toml_is_auto_detected(tmp_path: Path) -> None:
    """A lints.toml at the root of a Git repo is auto-applied without passing --config."""
    repo_dir = tmp_path / "my_repo"
    sub_dir = repo_dir / "src" / "nested"
    sub_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(repo_dir)], check=True)
    (repo_dir / "lints.toml").write_text(
        '[lints]\ntarget = "src"\n[py]\nno-blind-except = false\nno-getattr = false\n'
        "[ts]\nno-default-export = false\n"
    )
    app_py = sub_dir / "app.py"
    app_py.write_text(BAD_PY)
    widget_ts = sub_dir / "widget.ts"
    widget_ts.write_text("export default function demo(): number {\n  return 1;\n}\n")

    assert _run_lints("target", cwd=sub_dir).stdout.strip() == "src"
    res_cwd = _run_lints("lint", cwd=sub_dir)
    assert res_cwd.returncode == 0, res_cwd.stdout + res_cwd.stderr
    res_explicit = _run_lints("lint", str(app_py), str(widget_ts))
    assert res_explicit.returncode == 0, res_explicit.stdout + res_explicit.stderr


def test_stray_lints_toml_outside_git_repo_is_ignored_without_config_flag(tmp_path: Path) -> None:
    """A stray ./lints.toml in a non-Git folder does not override central config.toml."""
    (tmp_path / "lints.toml").write_text(
        '[lints]\ntarget = "custom_dir"\n[py]\nno-blind-except = false\nno-getattr = false\n'
    )
    bad_py = tmp_path / "bad.py"
    bad_py.write_text(BAD_PY)
    assert _run_lints("target", cwd=tmp_path).stdout.strip() == "."
    res = _run_lints("lint", str(bad_py), cwd=tmp_path)
    assert res.returncode == 1
    assert "BLE001" in res.stdout
    assert "PY006" in res.stdout


def test_missing_config_file_fails_fast(tmp_path: Path) -> None:
    """Passing a missing --config path fails immediately with exit code 2."""
    res = _run_lints("lint", "--config", str(tmp_path / "does-not-exist.toml"))
    assert res.returncode == 2
    assert "Config file not found" in res.stderr
