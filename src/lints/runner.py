"""Lint execution, custom Python AST runner, rule scaffolder, and hermetic test runner."""

from __future__ import annotations

import ast
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from lints.config import (
    CONFIG_TOML,
    GENERATED_OXLINT_CONFIG,
    GENERATED_RUFF_TOML,
    REPO_DIR,
    LintsConfig,
    RuleSpec,
    build_artifacts,
    discover_rules,
    load_toml_config,
    resolve_effective_config,
    resolve_rules_root,
    set_rule_enabled,
)

PY_EXTS = {".py", ".pyi"}
TS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".mts", ".cjs", ".cts"}
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    "out",
    "target",
    ".mypy_cache",
    ".ruff_cache",
}

PyCheckFn = Callable[[ast.AST, Path], list[tuple[int, int, str]]]


@dataclass
class PartitionedTargets:
    py_targets: list[str]
    py_files: list[Path]
    ts_targets: list[str]


@dataclass
class RuleTestResult:
    rule_id: str
    passed: bool
    detail: str


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=capture,
    )


def resolve_ruff_cmd() -> list[str]:
    ruff_bin = shutil.which("ruff")
    if ruff_bin:
        return [ruff_bin]
    if shutil.which("uv"):
        return ["uv", "run", "--quiet", "--project", str(REPO_DIR), "ruff"]
    return ["ruff"]


def resolve_oxlint_cmd() -> list[str] | None:
    oxlint_bin = shutil.which("oxlint")
    if oxlint_bin:
        return [oxlint_bin]
    if shutil.which("bunx"):
        return ["bunx", "oxlint"]
    if shutil.which("npx"):
        return ["npx", "--yes", "oxlint"]
    return None


def is_python_script(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in PY_EXTS:
        return True
    if ext:
        return False
    try:
        with path.open("rb") as fh:
            first_line = fh.readline(128)
        return first_line.startswith(b"#!") and b"python" in first_line
    except OSError:
        return False


def _is_rule_test_fixture(path: Path) -> bool:
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(REPO_DIR)
    except ValueError:
        return False
    parts = rel.parts
    return len(parts) >= 4 and parts[0] == "rules" and "tests" in parts


def partition_targets(targets: list[str]) -> PartitionedTargets:
    py_targets: list[str] = []
    py_files: list[Path] = []
    ts_targets: list[str] = []

    for raw in targets:
        p = Path(raw).expanduser()
        if p.is_file():
            ext = p.suffix.lower()
            if is_python_script(p):
                py_targets.append(str(p))
                py_files.append(p)
            if ext in TS_EXTS:
                ts_targets.append(str(p))
        elif p.is_dir():
            dir_has_py = False
            dir_has_ts = False
            shebang_scripts: list[str] = []
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                root_path = Path(root)
                if _is_rule_test_fixture(root_path):
                    dirs[:] = []
                    continue
                for fname in files:
                    fpath = root_path / fname
                    if _is_rule_test_fixture(fpath):
                        continue
                    ext = fpath.suffix.lower()
                    if ext in PY_EXTS:
                        dir_has_py = True
                        py_files.append(fpath)
                    elif not ext and is_python_script(fpath):
                        shebang_scripts.append(str(fpath))
                        py_files.append(fpath)
                    elif ext in TS_EXTS:
                        dir_has_ts = True
            if dir_has_py:
                py_targets.append(str(p))
            py_targets.extend(shebang_scripts)
            if dir_has_ts:
                ts_targets.append(str(p))

    return PartitionedTargets(
        py_targets=list(dict.fromkeys(py_targets)),
        py_files=list(dict.fromkeys(py_files)),
        ts_targets=list(dict.fromkeys(ts_targets)),
    )


def load_py_rule_fn(py_file: Path) -> PyCheckFn | None:
    spec = importlib.util.spec_from_file_location(f"lints_rule_{py_file.parent.name}", py_file)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = mod.__dict__.get("check")
    if callable(fn):
        return fn
    return None


def _line_has_noqa(line: str, code: str, rule_name: str) -> bool:
    if "# noqa" not in line:
        return False
    idx = line.index("# noqa")
    tail = line[idx + len("# noqa") :].strip()
    if not tail or tail.startswith("#"):
        return True
    if tail.startswith(":"):
        tokens = [tok.strip() for tok in tail[1:].split(",")]
        return code in tokens or rule_name in tokens
    return False


def run_python_ast_rules(py_files: list[Path], rules: list[RuleSpec]) -> int:
    active_checkers: list[tuple[RuleSpec, str, PyCheckFn]] = []
    for spec in rules:
        if spec.lang != "py" or not spec.enabled:
            continue
        py_file = spec.custom_py_file
        if py_file is None:
            continue
        fn = load_py_rule_fn(py_file)
        if fn is not None:
            code = str(spec.meta.get("code", spec.name))
            active_checkers.append((spec, code, fn))

    if not active_checkers or not py_files:
        return 0

    violations_count = 0
    for fpath in sorted(py_files):
        try:
            source = fpath.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(fpath))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        source_lines = source.splitlines()
        for spec, code, fn in active_checkers:
            for line_no, col_no, message in fn(tree, fpath):
                src_line = source_lines[line_no - 1] if 1 <= line_no <= len(source_lines) else ""
                if _line_has_noqa(src_line, code, spec.name):
                    continue
                print(f"{fpath}:{line_no}:{col_no}: {code} [{spec.rule_id}] {message}")
                violations_count += 1

    return 1 if violations_count > 0 else 0


def ensure_built() -> None:
    if not GENERATED_OXLINT_CONFIG.exists() or not GENERATED_RUFF_TOML.exists():
        build_artifacts()


def resolve_default_targets(
    raw_paths: list[str], cfg: LintsConfig, local_cfg_path: Path | None
) -> list[str]:
    if raw_paths:
        return raw_paths
    base_dir = local_cfg_path.parent if local_cfg_path is not None else Path.cwd()
    target_path = Path(cfg.target).expanduser()
    if target_path.is_absolute():
        return [str(target_path)]
    return [str((base_dir / target_path).resolve())]


def run_lint(raw_paths: list[str], *, fix: bool = False) -> int:
    ensure_built()
    eff_cfg, local_cfg_path = resolve_effective_config(Path.cwd())
    targets = resolve_default_targets(raw_paths, eff_cfg, local_cfg_path)
    part = partition_targets(targets)

    if not part.py_targets and not part.ts_targets:
        print(f"No Python or JS/TS files found in {', '.join(targets)}")
        return 0

    rules = discover_rules(eff_cfg)
    exit_code = 0

    if part.py_targets:
        ruff = resolve_ruff_cmd()
        ruff_cfg = ["--config", str(GENERATED_RUFF_TOML)]
        if fix:
            print("==> ruff check --fix")
            r1 = run_cmd([*ruff, "check", "--fix", *ruff_cfg, *part.py_targets])
            print("==> ruff format")
            r2 = run_cmd([*ruff, "format", *ruff_cfg, *part.py_targets])
            if r1.returncode != 0 or r2.returncode != 0:
                exit_code = 1
        else:
            print("==> ruff check")
            r1 = run_cmd([*ruff, "check", *ruff_cfg, *part.py_targets])
            if r1.returncode != 0:
                exit_code = 1

        ast_rc = run_python_ast_rules(part.py_files, rules)
        if ast_rc != 0:
            exit_code = 1

    if part.ts_targets:
        oxlint = resolve_oxlint_cmd()
        if oxlint is None:
            print("error: oxlint not found (run `lints bootstrap`)", file=sys.stderr)
            exit_code = 1
        else:
            ox_cfg = ["-c", str(REPO_DIR / "oxlint.config.ts")]
            flag = ["--fix"] if fix else []
            label = "oxlint --fix" if fix else "oxlint"
            print(f"==> {label}")
            r3 = run_cmd([*oxlint, *flag, *ox_cfg, *part.ts_targets])
            if r3.returncode != 0:
                exit_code = 1

    return exit_code


def _collect_test_cases(tests_dir: Path, prefix: str) -> list[tuple[Path, Path]]:
    """Return `(source_file, relative_target_under_src)` pairs for `invalid` or `valid` cases."""
    cases: list[tuple[Path, Path]] = []
    if not tests_dir.is_dir():
        return cases

    sub_dir = tests_dir / prefix
    if sub_dir.is_dir():
        cases.extend(
            (fpath, fpath.relative_to(sub_dir))
            for fpath in sorted(sub_dir.rglob("*"))
            if fpath.is_file()
        )

    cases.extend(
        (fpath, Path(fpath.name))
        for fpath in sorted(tests_dir.iterdir())
        if fpath.is_file()
        and (
            fpath.stem == prefix
            or fpath.name.startswith(f"{prefix}.")
            or fpath.name.startswith(f"{prefix}-")
        )
    )

    return cases


def _test_ts_rule(spec: RuleSpec, oxlint: list[str]) -> RuleTestResult:
    tests_dir = spec.folder / "tests"
    invalid_cases = _collect_test_cases(tests_dir, "invalid")
    valid_cases = _collect_test_cases(tests_dir, "valid")
    if not invalid_cases or not valid_cases:
        return RuleTestResult(
            spec.rule_id, False, "missing `tests/invalid*` or `tests/valid*` fixture"
        )

    with tempfile.TemporaryDirectory(prefix=f"lints-test-{spec.name}-") as tmp:
        tmp_dir = Path(tmp)
        plugins: list[str] = []
        rules: dict[str, object] = {}
        overrides: list[dict[str, object]] = []
        js_plugins: list[str] = []

        ox_meta = spec.meta.get("oxlint")
        if isinstance(ox_meta, dict):
            raw_plugins = ox_meta.get("plugins")
            if isinstance(raw_plugins, list):
                plugins.extend(str(p) for p in raw_plugins)
            raw_rules = ox_meta.get("rules")
            if isinstance(raw_rules, dict):
                rules.update(raw_rules)
            raw_overrides = ox_meta.get("overrides")
            if isinstance(raw_overrides, list):
                overrides.extend(ov for ov in raw_overrides if isinstance(ov, dict))

        ts_file = spec.custom_ts_file
        if ts_file is not None:
            plugin_path = tmp_dir / "plugin.ts"
            plugin_path.write_text(
                f'import {{ rule }} from "{ts_file.as_posix()}";\n'
                f'export default {{ meta: {{ name: "lints" }}, rules: {{ "{spec.name}": rule }} }};\n',
                encoding="utf-8",
            )
            js_plugins.append(plugin_path.as_posix())
            default_sev = str(spec.meta.get("defaultSeverity", "error"))
            if default_sev != "off":
                rules[f"lints/{spec.name}"] = default_sev

        cfg_path = tmp_dir / "oxlint.config.ts"
        cfg_payload = {
            "plugins": plugins,
            "categories": {"correctness": "off", "suspicious": "off"},
            "jsPlugins": js_plugins,
            "rules": rules,
            "overrides": overrides,
        }
        cfg_path.write_text(
            f"export default {json.dumps(cfg_payload, indent=2)};\n",
            encoding="utf-8",
        )

        for src_file, rel_dest in invalid_cases:
            dest = tmp_dir / "case_invalid" / "src" / rel_dest
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
            res = run_cmd([*oxlint, "-c", str(cfg_path), str(dest)], capture=True)
            if res.returncode == 0:
                return RuleTestResult(
                    spec.rule_id,
                    False,
                    f"expected invalid fixture `{src_file.name}` to fail, but it passed",
                )

        for src_file, rel_dest in valid_cases:
            dest = tmp_dir / "case_valid" / "src" / rel_dest
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
            res = run_cmd([*oxlint, "-c", str(cfg_path), str(dest)], capture=True)
            if res.returncode != 0:
                out = (res.stdout or res.stderr).strip()
                return RuleTestResult(
                    spec.rule_id,
                    False,
                    f"expected valid fixture `{src_file.name}` to pass, got:\n{out}",
                )

    return RuleTestResult(
        spec.rule_id, True, f"{len(invalid_cases)} invalid + {len(valid_cases)} valid ok"
    )


def _test_py_rule(spec: RuleSpec, ruff: list[str]) -> RuleTestResult:
    tests_dir = spec.folder / "tests"
    invalid_cases = _collect_test_cases(tests_dir, "invalid")
    valid_cases = _collect_test_cases(tests_dir, "valid")
    if not invalid_cases or not valid_cases:
        return RuleTestResult(
            spec.rule_id, False, "missing `tests/invalid*` or `tests/valid*` fixture"
        )

    ruff_meta = spec.meta.get("ruff")
    select_codes: list[str] = []
    ignore_codes: list[str] = []
    banned_api: dict[str, str] = {}
    per_file_ignores: dict[str, list[str]] = {}

    if isinstance(ruff_meta, dict):
        raw_sel = ruff_meta.get("select")
        if isinstance(raw_sel, list):
            select_codes = [str(c) for c in raw_sel]
        raw_ign = ruff_meta.get("ignore")
        if isinstance(raw_ign, list):
            ignore_codes = [str(c) for c in raw_ign]
        raw_ban = ruff_meta.get("bannedApi")
        if isinstance(raw_ban, dict):
            banned_api = {str(k): str(v) for k, v in raw_ban.items()}
        raw_pfi = ruff_meta.get("perFileIgnores")
        if isinstance(raw_pfi, dict):
            for k, v in raw_pfi.items():
                if isinstance(v, list):
                    per_file_ignores[str(k)] = [str(x) for x in v]

    py_fn = load_py_rule_fn(spec.custom_py_file) if spec.custom_py_file else None

    with tempfile.TemporaryDirectory(prefix=f"lints-test-{spec.name}-") as tmp:
        tmp_dir = Path(tmp)
        ruff_cfg_path: Path | None = None
        if select_codes:
            ruff_cfg_path = tmp_dir / "ruff.toml"
            lines = [
                'target-version = "py312"',
                "[lint]",
                f"select = {json.dumps(select_codes)}",
                f"ignore = {json.dumps(ignore_codes)}",
            ]
            if banned_api:
                lines.append("[lint.flake8-tidy-imports.banned-api]")
                for api, msg in banned_api.items():
                    lines.append(f"{json.dumps(api)} = {{ msg = {json.dumps(msg)} }}")
            if per_file_ignores:
                lines.append("[lint.per-file-ignores]")
                for pat, codes in per_file_ignores.items():
                    lines.append(f"{json.dumps(pat)} = {json.dumps(codes)}")
            ruff_cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        def evaluate_case(src_file: Path, rel_dest: Path, subdir: str) -> tuple[bool, str]:
            dest = tmp_dir / subdir / "src" / rel_dest
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
            failed = False
            details: list[str] = []

            if ruff_cfg_path is not None:
                res = run_cmd(
                    [*ruff, "check", "--config", str(ruff_cfg_path), str(dest)], capture=True
                )
                if res.returncode != 0:
                    failed = True
                    details.append((res.stdout or res.stderr).strip())

            if py_fn is not None:
                tree = ast.parse(dest.read_text(encoding="utf-8"), filename=str(dest))
                rel_check_path = Path("src") / rel_dest
                issues = py_fn(tree, rel_check_path)
                if issues:
                    failed = True
                    details.extend(msg for _, _, msg in issues)

            return failed, "\n".join(details)

        for src_file, rel_dest in invalid_cases:
            failed, _ = evaluate_case(src_file, rel_dest, "invalid")
            if not failed:
                return RuleTestResult(
                    spec.rule_id,
                    False,
                    f"expected invalid fixture `{src_file.name}` to fail, but it passed",
                )

        for src_file, rel_dest in valid_cases:
            failed, out = evaluate_case(src_file, rel_dest, "valid")
            if failed:
                return RuleTestResult(
                    spec.rule_id,
                    False,
                    f"expected valid fixture `{src_file.name}` to pass, got:\n{out}",
                )

    return RuleTestResult(
        spec.rule_id, True, f"{len(invalid_cases)} invalid + {len(valid_cases)} valid ok"
    )


def run_rule_tests(filter_query: str | None = None) -> int:
    all_rules = discover_rules()
    selected = [
        r for r in all_rules if filter_query is None or filter_query in {r.rule_id, r.name, r.lang}
    ]
    if not selected:
        print(f"error: no rule matching `{filter_query}`", file=sys.stderr)
        return 1

    ruff = resolve_ruff_cmd()
    oxlint = resolve_oxlint_cmd()
    if any(r.lang == "ts" for r in selected) and oxlint is None:
        print("error: oxlint is required to run TypeScript rule tests", file=sys.stderr)
        return 1

    def run_one(spec: RuleSpec) -> RuleTestResult:
        if spec.lang == "ts":
            assert oxlint is not None
            return _test_ts_rule(spec, oxlint)
        return _test_py_rule(spec, ruff)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run_one, selected))

    failures = 0
    for res in results:
        status = "PASS" if res.passed else "FAIL"
        print(f"  [{status}] {res.rule_id:<34} {res.detail}")
        if not res.passed:
            failures += 1

    if failures:
        print(f"\n{failures} rule test(s) failed.", file=sys.stderr)
        return 1
    print(f"\nAll {len(results)} rule(s) passed hermetic tests.")
    return 0


def scaffold_new_rule(raw_id: str, summary: str) -> int:
    if "/" not in raw_id:
        print(
            "error: specify `<ts|py>/<rule-name>`, e.g. `lints new ts/no-date-now`", file=sys.stderr
        )
        return 1
    lang, name = raw_id.split("/", 1)
    if lang not in {"ts", "py"} or not name:
        print("error: language prefix must be `ts` or `py`", file=sys.stderr)
        return 1

    cfg = load_toml_config(CONFIG_TOML)
    rules_root = resolve_rules_root(cfg)
    folder = rules_root / lang / name
    if folder.exists():
        print(f"error: rule folder already exists at {folder}", file=sys.stderr)
        return 1

    (folder / "tests").mkdir(parents=True, exist_ok=True)
    desc = summary or f"Enforce `{name}`."

    if lang == "ts":
        (folder / "rule.json").write_text(
            json.dumps({"summary": desc}, indent=2) + "\n",
            encoding="utf-8",
        )
        (folder / "README.md").write_text(
            f"# `ts/{name}`\n\n## Why\n{desc}\n\n## How to Fix\nReplace the disallowed pattern with the canonical alternative shown in `tests/valid.ts`.\n",
            encoding="utf-8",
        )
        (folder / "rule.ts").write_text(
            'import { type RuleDefinition } from "../types.ts";\n\n'
            "export const rule: RuleDefinition = {\n"
            "  meta: {\n"
            '    type: "problem",\n'
            f"    docs: {{ description: {json.dumps(desc)} }},\n"
            "  },\n"
            "  create(context) {\n"
            "    return {\n"
            "      Identifier(node) {\n"
            '        if (node.name === "FORBIDDEN_EXAMPLE") {\n'
            "          context.report({\n"
            "            node,\n"
            f'            message: "Forbidden pattern. Fix: see `lints explain ts/{name}`.",\n'
            "          });\n"
            "        }\n"
            "      },\n"
            "    };\n"
            "  },\n"
            "};\n",
            encoding="utf-8",
        )
        (folder / "tests" / "invalid.ts").write_text(
            "export const FORBIDDEN_EXAMPLE = 1;\n",
            encoding="utf-8",
        )
        (folder / "tests" / "valid.ts").write_text(
            "export const cleanValue = 1;\n",
            encoding="utf-8",
        )
    else:
        code = f"PY9{len(discover_rules(cfg)):02d}"
        (folder / "rule.json").write_text(
            json.dumps({"code": code, "summary": desc}, indent=2) + "\n",
            encoding="utf-8",
        )
        (folder / "README.md").write_text(
            f"# `py/{name}` (`{code}`)\n\n## Why\n{desc}\n\n## How to Fix\nSee `tests/valid.py`.\n",
            encoding="utf-8",
        )
        (folder / "rule.py").write_text(
            f'"""Custom AST rule: `py/{name}` (`{code}`)."""\n\n'
            "from __future__ import annotations\n\n"
            "import ast\n"
            "from pathlib import Path\n\n\n"
            "def check(tree: ast.AST, _path: Path) -> list[tuple[int, int, str]]:\n"
            "    return [\n"
            "        (\n"
            "            node.lineno,\n"
            "            node.col_offset + 1,\n"
            f'            "Forbidden pattern. Fix: see `lints explain py/{name}`.",\n'
            "        )\n"
            "        for node in ast.walk(tree)\n"
            '        if isinstance(node, ast.Name) and node.id == "FORBIDDEN_EXAMPLE"\n'
            "    ]\n",
            encoding="utf-8",
        )
        (folder / "tests" / "invalid.py").write_text(
            "FORBIDDEN_EXAMPLE = 1\n",
            encoding="utf-8",
        )
        (folder / "tests" / "valid.py").write_text(
            "CLEAN_VALUE = 1\n",
            encoding="utf-8",
        )

    set_rule_enabled(lang, name, True, CONFIG_TOML)
    build_artifacts()
    print(f"Created rule `{lang}/{name}` at {folder}")
    print(f"Next: edit `{folder}` and verify with `lints test {lang}/{name}`.")
    return 0


def explain_rule(query: str) -> int:
    matches = [
        r for r in discover_rules() if query in {r.rule_id, r.name, str(r.meta.get("code", ""))}
    ]
    if not matches:
        print(
            f"error: no rule matching `{query}` (run `lints list` to see all rules)",
            file=sys.stderr,
        )
        return 1

    for spec in matches:
        readme = spec.folder / "README.md"
        if readme.exists():
            print(readme.read_text(encoding="utf-8").rstrip())
        tests_dir = spec.folder / "tests"
        for label in ("invalid", "valid"):
            for src_file, _ in _collect_test_cases(tests_dir, label):
                print(f"\n### {label.upper()} ({src_file.relative_to(spec.folder)})")
                print("```")
                print(src_file.read_text(encoding="utf-8").rstrip())
                print("```")
    return 0
