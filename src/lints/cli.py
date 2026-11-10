"""Minimal uv + Typer CLI for self-contained Ruff & Oxlint rules."""

from __future__ import annotations

import ast
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
import datetime as dt
from enum import StrEnum
import importlib.util
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import tomllib

from pydantic import BaseModel, Field
import tomlkit
import typer

from lints.noqa import is_noqa_suppressed

REPO_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_TOML = REPO_DIR / "config.toml"
RUFF_TOML = REPO_DIR / "ruff.toml"
GEN_DIR = REPO_DIR / ".generated"
GEN_CONFIG = GEN_DIR / "oxlint-config.json"
GEN_PLUGIN = GEN_DIR / "oxlint-plugin.ts"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.lints.sync.plist"
CRON_TAG = "# lints-sync"

PY_EXTS = {".py", ".pyi"}
TS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".mts"}
DEFAULT_IGNORE = [
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    "out",
]
PyCheckFn = Callable[[ast.AST, Path], list[tuple[int, int, str]]]
CONFIG_OPTION = typer.Option(
    None,
    "--config",
    "-c",
    help="Path to a config TOML file that overrides the default config.toml.",
)

app = typer.Typer(
    help="Centralised Ruff + Oxlint rules managed via config.toml.", no_args_is_help=False
)


class OxlintMeta(BaseModel):
    plugins: list[str] = []
    rules: dict[str, object] = {}
    overrides: list[dict[str, object]] = []


class RuffMeta(BaseModel):
    select: list[str] = []
    ignore: list[str] = []
    banned_api: dict[str, str] = Field(default={}, alias="bannedApi")
    per_file_ignores: dict[str, list[str]] = Field(default={}, alias="perFileIgnores")


class RuleMeta(BaseModel):
    summary: str
    code: str | None = None
    default_severity: str = Field(default="error", alias="defaultSeverity")
    oxlint: OxlintMeta = OxlintMeta()
    ruff: RuffMeta = RuffMeta()


class LintsSettings(BaseModel):
    target: str = "."
    ignore: list[str] = Field(default_factory=lambda: list(DEFAULT_IGNORE))
    rules_dir: str = "rules"
    checklists_dir: str = "checklists"


class ConfigFile(BaseModel):
    lints: LintsSettings = LintsSettings()
    checklists: dict[str, bool] = {}
    ts: dict[str, bool] = {}
    py: dict[str, bool] = {}


@dataclass
class Rule:
    lang: str
    name: str
    folder: Path
    enabled: bool
    meta: RuleMeta

    @property
    def id(self) -> str:
        return f"{self.lang}/{self.name}"

    @property
    def ts_file(self) -> Path | None:
        p = self.folder / "rule.ts"
        return p if p.exists() else None

    @property
    def py_file(self) -> Path | None:
        p = self.folder / "rule.py"
        return p if p.exists() else None


def _setup_path() -> str:
    h = str(Path.home())
    extra = ["/opt/homebrew/bin", "/usr/local/bin", f"{h}/.local/bin", f"{h}/.bun/bin"]
    merged = list(dict.fromkeys([*extra, *os.environ.get("PATH", "/usr/bin:/bin").split(":")]))
    os.environ["PATH"] = ":".join(p for p in merged if p)
    return os.environ["PATH"]


def _find_repo_config(start: Path | None = None) -> Path | None:
    anchor = (start or Path.cwd()).expanduser().resolve()
    cur = anchor if anchor.is_dir() else anchor.parent
    for d in (cur, *cur.parents):
        if (d / ".git").exists():
            candidate = d / "lints.toml"
            if candidate.is_file() and candidate != CONFIG_TOML.resolve():
                return candidate
            return None
    return None


def _load_config(
    config: Path | None = None,
    *,
    start: Path | None = None,
    auto_detect: bool = True,
) -> tuple[ConfigFile, Path | None]:
    if config is not None:
        resolved = config.expanduser().resolve()
        if not resolved.is_file():
            raise typer.BadParameter(f"Config file not found: {config}", param_hint="'--config'")
        return ConfigFile.model_validate(tomllib.loads(resolved.read_text())), resolved
    if auto_detect and (repo_cfg := _find_repo_config(start)) is not None:
        return ConfigFile.model_validate(tomllib.loads(repo_cfg.read_text())), repo_cfg
    if CONFIG_TOML.exists():
        return ConfigFile.model_validate(tomllib.loads(CONFIG_TOML.read_text())), None
    return ConfigFile(), None


def _rules(cfg: ConfigFile | None = None) -> list[Rule]:
    active = cfg or _load_config()[0]
    root = (REPO_DIR / Path(active.lints.rules_dir).expanduser()).resolve()
    out: list[Rule] = []
    for lang, toggles in (("ts", active.ts), ("py", active.py)):
        if not (root / lang).is_dir():
            continue
        for folder in sorted((root / lang).iterdir()):
            rj = folder / "rule.json"
            if folder.is_dir() and rj.exists():
                meta = RuleMeta.model_validate_json(rj.read_text())
                out.append(Rule(lang, folder.name, folder, toggles.get(folder.name, True), meta))
    return out


def _oxlint_cmd() -> list[str]:
    if shutil.which("oxlint"):
        return ["oxlint"]
    if shutil.which("bunx"):
        return ["bunx", "oxlint"]
    return ["npx", "--yes", "oxlint"]


def _load_py_fn(path: Path) -> PyCheckFn | None:
    spec = importlib.util.spec_from_file_location(f"rule_{path.parent.name}", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = mod.__dict__.get("check")
    return fn if callable(fn) else None


def _compile_configs(
    cfg: ConfigFile,
    rules: list[Rule],
    *,
    plugin_path: Path,
    oxlint_json_path: Path | None,
    ruff_path: Path,
    relative_to_repo: bool,
) -> dict[str, object]:
    plugins = ["typescript", "unicorn", "import", "oxc"]
    ox_rules: dict[str, object] = {
        "eqeqeq": ["error", "smart"],
        "prefer-const": "error",
        "no-var": "error",
        "no-eval": "error",
        "no-empty": ["error", {"allowEmptyCatch": False}],
        "no-unused-vars": ["error", {"argsIgnorePattern": "^_", "varsIgnorePattern": "^_"}],
        "typescript/consistent-type-imports": [
            "error",
            {"prefer": "type-imports", "fixStyle": "inline-type-imports"},
        ],
        "unicorn/prefer-node-protocol": "error",
        "unicorn/consistent-function-scoping": "off",
        "import/no-cycle": "error",
        "import/default": "off",
    }
    overrides: list[dict[str, object]] = []
    imports: list[str] = []
    entries: list[str] = []

    for r in [x for x in rules if x.lang == "ts" and x.enabled]:
        plugins.extend(p for p in r.meta.oxlint.plugins if p not in plugins)
        ox_rules.update(r.meta.oxlint.rules)
        overrides.extend(r.meta.oxlint.overrides)
        if r.ts_file:
            ident = f"r_{len(imports)}"
            rel = (Path("..") / r.ts_file.relative_to(REPO_DIR)) if relative_to_repo else r.ts_file
            imports.append(f'import {{ rule as {ident} }} from "{rel.as_posix()}";')
            entries.append(f'    "{r.name}": {ident},')
            if r.meta.default_severity != "off":
                ox_rules[f"lints/{r.name}"] = r.meta.default_severity

    plugin_path.write_text(
        "\n".join(
            [*imports, "", 'export default { meta: { name: "lints" }, rules: {', *entries, "}};\n"]
        ),
    )
    ox_doc: dict[str, object] = {
        "plugins": plugins,
        "categories": {"correctness": "error", "suspicious": "warn"},
        "hasCustomPlugin": bool(entries),
        "rules": ox_rules,
        "overrides": overrides,
        "ignorePatterns": [
            *(f"{p.rstrip('/')}/**" for p in cfg.lints.ignore),
            "rules/**/tests/**",
        ],
    }
    if oxlint_json_path is not None:
        oxlint_json_path.write_text(json.dumps(ox_doc, indent=2) + "\n")

    select = [
        "E4",
        "E7",
        "E9",
        "F",
        "I",
        "B",
        "UP",
        "SIM",
        "C4",
        "PIE",
        "RET",
        "TID252",
        "PTH",
        "PLE",
        "PERF",
        "FURB",
        "RUF",
    ]
    ignore = ["E501", "B008", "RET504", "PTH123"]
    banned: dict[str, dict[str, str]] = {}
    pfi: dict[str, list[str]] = {}
    external = sorted({r.meta.code for r in rules if r.lang == "py" and r.meta.code})
    for r in [x for x in rules if x.lang == "py" and x.enabled]:
        select.extend(c for c in r.meta.ruff.select if c not in select)
        ignore.extend(c for c in r.meta.ruff.ignore if c not in ignore)
        banned.update({k: {"msg": v} for k, v in r.meta.ruff.banned_api.items()})
        for pat, codes in r.meta.ruff.per_file_ignores.items():
            pfi.setdefault(pat, []).extend(c for c in codes if c not in pfi.get(pat, []))

    ruff_doc: dict[str, object] = {
        "line-length": 100,
        "target-version": "py312",
        "exclude": [*cfg.lints.ignore, "rules/**/tests/**"],
        "lint": {
            "select": select,
            "ignore": ignore,
            **({"external": external} if external else {}),
            "flake8-tidy-imports": {
                "ban-relative-imports": "parents",
                **({"banned-api": banned} if banned else {}),
            },
            "isort": {"combine-as-imports": True, "force-sort-within-sections": True},
            **({"per-file-ignores": pfi} if pfi else {}),
        },
        "format": {"quote-style": "double", "indent-style": "space"},
    }
    ruff_path.write_text(
        "# Auto-generated by `lints build` from `config.toml`.\n\n" + tomlkit.dumps(ruff_doc)
    )
    return ox_doc


@app.command()
def build() -> None:
    """Compile enabled rules from config.toml into ruff.toml and .generated/."""
    cfg, _ = _load_config(auto_detect=False)
    GEN_DIR.mkdir(exist_ok=True)
    _compile_configs(
        cfg,
        _rules(cfg),
        plugin_path=GEN_PLUGIN,
        oxlint_json_path=GEN_CONFIG,
        ruff_path=RUFF_TOML,
        relative_to_repo=True,
    )


def _is_ignored_rel(rel_parts: tuple[str, ...], ignore: list[str]) -> bool:
    for raw in ignore:
        if not (pat := tuple(Path(raw.strip("/")).parts)):
            continue
        if (len(pat) == 1 and pat[0] in rel_parts) or any(
            rel_parts[i : i + len(pat)] == pat for i in range(len(rel_parts) - len(pat) + 1)
        ):
            return True
    return False


def _collect_files(
    targets: list[Path], ignore: list[str] = DEFAULT_IGNORE, base_dir: Path | None = None
) -> tuple[list[Path], list[Path]]:
    py_files: list[Path] = []
    ts_files: list[Path] = []
    base_res = base_dir.resolve() if base_dir else None
    for t in targets:
        if t.is_file():
            tf = t.resolve()
            if (
                base_res
                and tf.is_relative_to(base_res)
                and _is_ignored_rel(tf.parent.relative_to(base_res).parts, ignore)
            ):
                continue
            if t.suffix in PY_EXTS:
                py_files.append(t)
            elif t.suffix in TS_EXTS:
                ts_files.append(t)
        elif t.is_dir():
            t_root = t.resolve()
            rel_root = base_res if (base_res and t_root.is_relative_to(base_res)) else t_root
            if rel_root != t_root and _is_ignored_rel(t_root.relative_to(rel_root).parts, ignore):
                continue
            for root, dirs, files in os.walk(t_root):
                rp = Path(root)
                dirs[:] = [
                    d
                    for d in dirs
                    if not _is_ignored_rel((rp / d).relative_to(rel_root).parts, ignore)
                ]
                if rp.resolve().is_relative_to(REPO_DIR / "rules") and "tests" in rp.parts:
                    dirs[:] = []
                    continue
                for f in files:
                    fp = rp / f
                    if fp.suffix in PY_EXTS:
                        py_files.append(fp)
                    elif fp.suffix in TS_EXTS:
                        ts_files.append(fp)
    return py_files, ts_files


@contextmanager
def _linter_configs(
    cfg: ConfigFile, rules: list[Rule], *, custom: bool
) -> Generator[tuple[Path, Path]]:
    if not custom:
        yield RUFF_TOML, REPO_DIR / "oxlint.config.ts"
        return
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        rcfg, plug, ocfg = td / "ruff.toml", td / "oxlint-plugin.ts", td / "oxlint.config.ts"
        ox_doc = _compile_configs(
            cfg,
            rules,
            plugin_path=plug,
            oxlint_json_path=None,
            ruff_path=rcfg,
            relative_to_repo=False,
        )
        js_plugins = [plug.as_posix()] if ox_doc.pop("hasCustomPlugin", False) else []
        ocfg.write_text(f"export default {json.dumps({**ox_doc, 'jsPlugins': js_plugins})};\n")
        yield rcfg, ocfg


def _run_lint(paths: list[Path] | None, *, fix: bool, config: Path | None = None) -> None:
    cfg, config_path = _load_config(config, start=paths[0] if paths else None)
    if config_path is None and (not GEN_CONFIG.exists() or not RUFF_TOML.exists()):
        build()
    base = config_path.parent if config_path else Path.cwd()
    targets = paths or [(base / Path(cfg.lints.target).expanduser()).resolve()]
    py_files, ts_files = _collect_files(targets, ignore=cfg.lints.ignore, base_dir=base)
    if not py_files and not ts_files:
        typer.echo("No Python or JS/TS files found.")
        return

    rules = _rules(cfg)
    rc = 0
    if py_files:
        py_targets = [str(p) for p in py_files]
        ruff = [shutil.which("ruff") or "ruff"]
        with _linter_configs(cfg, rules, custom=config_path is not None) as (ruff_cfg, _):
            if fix:
                rc |= subprocess.call(
                    [*ruff, "check", "--fix", "--config", str(ruff_cfg), *py_targets]
                )
                rc |= subprocess.call([*ruff, "format", "--config", str(ruff_cfg), *py_targets])
            else:
                rc |= subprocess.call([*ruff, "check", "--config", str(ruff_cfg), *py_targets])

        checkers = [
            (r, r.meta.code or r.name, fn)
            for r in rules
            if r.lang == "py" and r.enabled and r.py_file and (fn := _load_py_fn(r.py_file))
        ]
        for fp in py_files:
            src = fp.read_text(errors="ignore")
            lines = src.splitlines()
            try:
                tree = ast.parse(src, filename=str(fp))
            except SyntaxError:
                rc = 1
                continue
            for r, code, fn in checkers:
                for ln, col, msg in fn(tree, fp):
                    if (
                        1 <= ln <= len(lines)
                        and "#" in lines[ln - 1]
                        and is_noqa_suppressed(src, ln, code, r.id)
                    ):
                        continue
                    typer.echo(f"{fp}:{ln}:{col}: {code} [{r.id}] {msg}")
                    rc = 1

    if ts_files:
        flags = ["--fix"] if fix else []
        ts_targets = [str(p) for p in ts_files]
        with _linter_configs(cfg, rules, custom=config_path is not None) as (_, oxlint_cfg):
            rc |= subprocess.call([*_oxlint_cmd(), *flags, "-c", str(oxlint_cfg), *ts_targets])

    if rc != 0:
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def default_cmd(ctx: typer.Context, config: Path | None = CONFIG_OPTION) -> None:
    _setup_path()
    if ctx.invoked_subcommand is None:
        _run_lint(None, fix=False, config=config)


@app.command()
def lint(
    paths: list[Path] | None = typer.Argument(None),
    config: Path | None = CONFIG_OPTION,
) -> None:
    """Lint configured target folder (or explicit paths)."""
    _run_lint(paths, fix=False, config=config)


@app.command()
def fix(
    paths: list[Path] | None = typer.Argument(None),
    config: Path | None = CONFIG_OPTION,
) -> None:
    """Auto-fix and format Python and TypeScript files."""
    _run_lint(paths, fix=True, config=config)


@app.command("list")
def list_rules(config: Path | None = CONFIG_OPTION) -> None:
    """List all self-contained rules and their enabled state."""
    cfg, _ = _load_config(config)
    typer.echo(f"target = {cfg.lints.target!r}   rules_dir = {cfg.lints.rules_dir!r}\n")
    for r in _rules(cfg):
        kind = "ast" if (r.ts_file or r.py_file) else "cfg"
        typer.echo(f"  [{'on ' if r.enabled else 'off'}] {r.id:<32} ({kind})  {r.meta.summary}")


def _set_toggle(query: str, *, value: bool, config: Path | None = None) -> None:
    matches = [r for r in _rules() if query in {r.id, r.name}]
    if not matches or (len(matches) > 1 and "/" not in query):
        typer.echo(
            f"Specify an exact rule ID from `lints list` (matched: {[m.id for m in matches]})",
            err=True,
        )
        raise typer.Exit(1)
    path = config.expanduser().resolve() if config is not None else CONFIG_TOML
    doc = tomlkit.parse(path.read_text()) if path.exists() else tomlkit.document()
    r = matches[0]
    if r.lang not in doc:
        doc[r.lang] = tomlkit.table()
    doc[r.lang][r.name] = value  # type: ignore[index]
    path.write_text(tomlkit.dumps(doc))
    if path == CONFIG_TOML:
        build()
    typer.echo(f"{'enabled' if value else 'disabled'} {r.id} in {path}")


@app.command()
def enable(rule: str, config: Path | None = CONFIG_OPTION) -> None:
    """Enable a rule in config.toml (or a standalone config via --config)."""
    _set_toggle(rule, value=True, config=config)


@app.command()
def disable(rule: str, config: Path | None = CONFIG_OPTION) -> None:
    """Disable a rule in config.toml (or a standalone config via --config)."""
    _set_toggle(rule, value=False, config=config)


@app.command()
def target(
    directory: str | None = typer.Argument(None),
    config: Path | None = CONFIG_OPTION,
) -> None:
    """Get or set the default folder linted by `lints lint`."""
    if directory is None:
        typer.echo(_load_config(config)[0].lints.target)
        return
    path = config.expanduser().resolve() if config is not None else CONFIG_TOML
    doc = tomlkit.parse(path.read_text()) if path.exists() else tomlkit.document()
    if "lints" not in doc:
        doc["lints"] = tomlkit.table()
    doc["lints"]["target"] = directory  # type: ignore[index]
    path.write_text(tomlkit.dumps(doc))
    typer.echo(f"Set target = {directory!r} in {path}")


@app.command()
def explain(rule: str) -> None:
    """Print a rule's README and valid/invalid test fixtures."""
    matches = [r for r in _rules() if rule in {r.id, r.name, r.meta.code}]
    if not matches:
        raise typer.BadParameter(f"Unknown rule `{rule}`")
    for r in matches:
        typer.echo((r.folder / "README.md").read_text().rstrip())
        for fp in sorted((r.folder / "tests").rglob("*")):
            if fp.is_file():
                typer.echo(f"\n### {fp.relative_to(r.folder)}\n```\n{fp.read_text().rstrip()}\n```")


@app.command()
def new(rule: str, summary: str = typer.Option("Enforce custom convention.", "--summary")) -> None:
    """Scaffold a new self-contained rule folder with tests."""
    lang, _, name = rule.partition("/")
    if lang not in {"ts", "py"} or not name:
        raise typer.BadParameter("Expected `<ts|py>/<rule-name>`, e.g. `ts/no-date-now`")
    folder = REPO_DIR / _load_config()[0].lints.rules_dir / lang / name
    (folder / "tests").mkdir(parents=True, exist_ok=False)
    (folder / "README.md").write_text(
        f"# `{rule}`\n\n## Why\n{summary}\n\n## How to Fix\nSee `tests/valid.{lang}`.\n"
    )
    if lang == "ts":
        (folder / "rule.json").write_text(json.dumps({"summary": summary}, indent=2) + "\n")
        (folder / "rule.ts").write_text(
            'import { type RuleDefinition } from "../types.ts";\n\n'
            f'export const rule: RuleDefinition = {{\n  meta: {{ type: "problem", docs: {{ description: {json.dumps(summary)} }} }},\n'
            '  create(ctx) {\n    return {\n      Identifier(node) {\n        if (node.name === "FORBIDDEN_EXAMPLE") '
            f'ctx.report({{ node, message: "Forbidden. Docs: `lints explain {rule}`." }});\n      }},\n    }};\n  }},\n}};\n'
        )
        (folder / "tests/invalid.ts").write_text("export const FORBIDDEN_EXAMPLE = 1;\n")
        (folder / "tests/valid.ts").write_text("export const ok = 1;\n")
    else:
        code = f"PY9{len(_rules()):02d}"
        (folder / "rule.json").write_text(
            json.dumps({"code": code, "summary": summary}, indent=2) + "\n"
        )
        (folder / "rule.py").write_text(
            "from __future__ import annotations\nimport ast\nfrom pathlib import Path\n\n"
            "def check(tree: ast.AST, _path: Path) -> list[tuple[int, int, str]]:\n"
            f'    return [(n.lineno, n.col_offset + 1, "Forbidden. Docs: `lints explain {rule}`.") '
            'for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "FORBIDDEN_EXAMPLE"]\n'
        )
        (folder / "tests/invalid.py").write_text("FORBIDDEN_EXAMPLE = 1\n")
        (folder / "tests/valid.py").write_text("OK = 1\n")
    _set_toggle(rule, value=True, config=None)


def _cases(tests_dir: Path, kind: str) -> list[tuple[Path, Path]]:
    sub = tests_dir / kind
    from_dir: list[tuple[Path, Path]] = []
    if sub.is_dir():
        from_dir = [(f, f.relative_to(sub)) for f in sorted(sub.rglob("*")) if f.is_file()]
    direct = [(f, Path(f.name)) for f in sorted(tests_dir.glob(f"{kind}*")) if f.is_file()]
    return [*from_dir, *direct]


class TestResult(BaseModel):
    rule_id: str
    ok: bool
    detail: str


def _test_one(r: Rule) -> TestResult:
    inv, val = _cases(r.folder / "tests", "invalid"), _cases(r.folder / "tests", "valid")
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        if r.lang == "ts":
            rules = dict(r.meta.oxlint.rules)
            js_plugins: list[str] = []
            if r.ts_file:
                plug = td / "plugin.ts"
                plug.write_text(
                    f'import {{ rule }} from "{r.ts_file.as_posix()}";\n'
                    f'export default {{ meta: {{ name: "lints" }}, rules: {{ "{r.name}": rule }} }};\n'
                )
                js_plugins.append(plug.as_posix())
                if r.meta.default_severity != "off":
                    rules[f"lints/{r.name}"] = r.meta.default_severity
            cfg = td / "oxlint.config.ts"
            cfg.write_text(
                "export default "
                + json.dumps(
                    {
                        "plugins": r.meta.oxlint.plugins,
                        "categories": {"correctness": "off", "suspicious": "off"},
                        "jsPlugins": js_plugins,
                        "rules": rules,
                        "overrides": r.meta.oxlint.overrides,
                    }
                )
            )
            ox = _oxlint_cmd()
            for kind, cases, expect_fail in (("invalid", inv, True), ("valid", val, False)):
                for src, rel in cases:
                    dest = td / kind / "src" / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    res = subprocess.run(
                        [*ox, "-c", str(cfg), str(dest)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if (res.returncode != 0) != expect_fail:
                        return TestResult(
                            rule_id=r.id, ok=False, detail=f"{kind} `{src.name}` unexpected result"
                        )
        else:
            rcfg = td / "ruff.toml"
            if r.meta.ruff.select:
                rcfg.write_text(
                    tomlkit.dumps(
                        {
                            "lint": {
                                "select": r.meta.ruff.select,
                                "ignore": r.meta.ruff.ignore,
                                "per-file-ignores": r.meta.ruff.per_file_ignores,
                                "flake8-tidy-imports": {
                                    "banned-api": {
                                        k: {"msg": v} for k, v in r.meta.ruff.banned_api.items()
                                    }
                                },
                            }
                        }
                    )
                )
            fn = _load_py_fn(r.py_file) if r.py_file else None
            for kind, cases, expect_fail in (("invalid", inv, True), ("valid", val, False)):
                for src, rel in cases:
                    dest = td / kind / "src" / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    failed = False
                    if r.meta.ruff.select:
                        res = subprocess.run(
                            ["ruff", "check", "--config", str(rcfg), str(dest)],
                            capture_output=True,
                            check=False,
                        )
                        failed = res.returncode != 0
                    if fn and fn(ast.parse(dest.read_text()), Path("src") / rel):
                        failed = True
                    if failed != expect_fail:
                        return TestResult(
                            rule_id=r.id, ok=False, detail=f"{kind} `{src.name}` unexpected result"
                        )
    return TestResult(rule_id=r.id, ok=True, detail=f"{len(inv)} invalid + {len(val)} valid ok")


@app.command("test")
def run_tests(rule: str | None = typer.Argument(None)) -> None:
    """Run hermetic invalid/valid fixture tests per rule."""
    selected = [r for r in _rules() if rule is None or rule in {r.id, r.name, r.lang}]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_test_one, selected))
    for res in results:
        typer.echo(f"  [{'PASS' if res.ok else 'FAIL'}] {res.rule_id:<32} {res.detail}")
    if not all(res.ok for res in results):
        raise typer.Exit(1)


def _render_checklists(cfg: ConfigFile | None = None) -> str:
    active = cfg or _load_config()[0]
    cdir = (REPO_DIR / Path(active.lints.checklists_dir).expanduser()).resolve()
    if not cdir.is_dir():
        return ""
    blocks = [
        md.read_text().strip()
        for md in sorted(cdir.glob("*.md"))
        if active.checklists.get(md.stem, True)
    ]
    return "\n\n".join(blocks)


@app.command()
def checklist(config: Path | None = CONFIG_OPTION) -> None:
    """Print enabled model self-check lists from checklists/."""
    typer.echo(_render_checklists(_load_config(config)[0]))


@app.command()
def sync(background: bool = typer.Option(False, "--background", hidden=True)) -> None:
    """Pull latest merged rules on main and rebuild configs."""
    branch = subprocess.check_output(
        ["git", "symbolic-ref", "--short", "HEAD"], cwd=REPO_DIR, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_DIR, text=True).strip()
    )
    if branch != "main":
        if background or dirty:
            return
        subprocess.run(["git", "checkout", "--quiet", "main"], cwd=REPO_DIR, check=True)
    subprocess.run(
        ["git", "pull", "--rebase", "--autostash", "--quiet", "origin", "main"],
        cwd=REPO_DIR,
        check=True,
    )
    build()
    if not background:
        typer.echo("Synced with origin/main and rebuilt configs.")


@app.command()
def propose(
    title: str = typer.Argument(""),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Run tests, push a branch, and open/update a PR on GitHub."""
    build()
    if not force:
        run_tests(None)

    host = socket.gethostname().split(".")[0]
    pr_title = title or f"chore: propose lint updates ({host})"
    slug = re.sub(r"[^a-z0-9]+", "-", pr_title.lower()).strip("-")[:36] or "update"

    branch = subprocess.check_output(
        ["git", "symbolic-ref", "--short", "HEAD"], cwd=REPO_DIR, text=True
    ).strip()
    if branch == "main":
        stamp = dt.datetime.now().strftime("%m%d-%H%M")
        branch = f"propose/{slug}-{stamp}"
        subprocess.run(["git", "checkout", "-b", branch], cwd=REPO_DIR, check=True)

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_DIR, text=True).strip():
        subprocess.run(["git", "add", "-A"], cwd=REPO_DIR, check=True)
        subprocess.run(["git", "commit", "-m", pr_title], cwd=REPO_DIR, check=True)

    subprocess.run(["git", "push", "-u", "origin", branch], cwd=REPO_DIR, check=True)

    existing = subprocess.run(
        ["gh", "pr", "view", branch, "--json", "url", "--jq", ".url"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if existing.returncode == 0 and existing.stdout.strip():
        typer.echo(f"Updated PR: {existing.stdout.strip()}")
    else:
        subprocess.run(
            ["gh", "pr", "create", "--title", pr_title, "--body", "Validated via `lints test`."],
            cwd=REPO_DIR,
            check=True,
        )


@app.command()
def merge(pr: str | None = typer.Argument(None)) -> None:
    """Squash-merge a proposed PR (defaults to current or latest open PR) and sync main."""
    target_pr = pr
    cur_branch = subprocess.check_output(
        ["git", "symbolic-ref", "--short", "HEAD"], cwd=REPO_DIR, text=True
    ).strip()
    if not target_pr and cur_branch == "main":
        listed = subprocess.check_output(
            [
                "gh",
                "pr",
                "list",
                "--limit",
                "1",
                "--json",
                "number",
                "--jq",
                ".[0].number // empty",
            ],
            cwd=REPO_DIR,
            text=True,
        ).strip()
        if not listed:
            typer.echo("No open PRs to merge.")
            return
        target_pr = listed

    cmd = ["gh", "pr", "merge", *([target_pr] if target_pr else []), "--squash", "--delete-branch"]
    subprocess.run(cmd, cwd=REPO_DIR, check=True)
    after_branch = subprocess.check_output(
        ["git", "symbolic-ref", "--short", "HEAD"], cwd=REPO_DIR, text=True
    ).strip()
    if after_branch != "main":
        subprocess.run(["git", "checkout", "main"], cwd=REPO_DIR, check=True)
    sync(background=False)


def _dirty_code_files(workspaces: list[str]) -> list[str]:
    dirty: list[str] = []
    for ws in workspaces:
        ws_path = Path(ws)
        if not ws_path.is_dir():
            continue
        res = subprocess.run(
            ["git", "status", "--porcelain", "-z", "-uall"],
            cwd=ws_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            continue
        entries = res.stdout.split("\0")
        idx = 0
        while idx < len(entries):
            entry = entries[idx]
            idx += 1
            if len(entry) < 4:
                continue
            status, rel = entry[:2], entry[3:]
            if "R" in status or "C" in status:
                idx += 1
            fp = (ws_path / rel).resolve()
            if fp.is_file() and (fp.suffix in PY_EXTS or fp.suffix in TS_EXTS):
                dirty.append(str(fp))
    return list(dict.fromkeys(dirty))


class HookAgent(StrEnum):
    ANTIGRAVITY = "antigravity"
    CLAUDE = "claude"
    CODEX = "codex"
    GIT = "git"


def _check_dirty_files_lint(workspaces: list[str]) -> tuple[bool, str]:
    files = _dirty_code_files(workspaces)
    if not files:
        return True, ""
    uv_bin = shutil.which("uv") or "uv"
    res = subprocess.run(
        [uv_bin, "run", "--quiet", "--project", str(REPO_DIR), "lints", "lint", *files],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.returncode == 0, (res.stdout + "\n" + res.stderr).strip()


def _filter_claude_codex_entries(entries: list[object], marker: str) -> list[object]:
    return [e for e in entries if marker not in json.dumps(e)]


class HookAction(StrEnum):
    INSTALL = "install"
    UNINSTALL = "uninstall"
    STOP = "stop"
    PRE_INVOCATION = "pre-invocation"


@app.command()
def hook(
    action: HookAction = typer.Argument(..., help="install | uninstall | stop | pre-invocation"),
    agent: HookAgent = typer.Option(..., "--agent", "-a", help="Target agent or harness"),
    local: bool = typer.Option(False, "--local", help="Install in current repo instead of global"),
) -> None:
    """Install or run pre-turn-end lint & checklist hooks (`--agent antigravity|claude|codex|git`)."""
    bin_cmd = str(REPO_DIR / "bin/lints")

    if action == HookAction.STOP:
        raw = sys.stdin.read().strip()
        payload = json.loads(raw) if raw else {}
        if agent == HookAgent.ANTIGRAVITY:
            if payload.get("terminationReason") != "NO_TOOL_CALL":
                sys.stdout.write(json.dumps({"decision": "allow"}) + "\n")
                return
            ok, out = _check_dirty_files_lint([str(p) for p in payload.get("workspacePaths", [])])
            if ok:
                sys.stdout.write(json.dumps({"decision": "allow"}) + "\n")
            else:
                reason = f"Pre-turn-end `lints` gate failed on modified files. Fix before finishing:\n\n{out}"
                sys.stdout.write(json.dumps({"decision": "continue", "reason": reason}) + "\n")
            return

        # Claude Code & Codex CLI pass `cwd` and `stop_hook_active`
        if payload.get("stop_hook_active"):
            return
        cwd = str(payload.get("cwd") or Path.cwd())
        ok, out = _check_dirty_files_lint([cwd])
        if not ok:
            reason = f"Pre-turn-end `lints` gate failed on modified files. Fix before finishing:\n\n{out}"
            if agent == HookAgent.CODEX:
                sys.stderr.write(reason + "\n")
                raise typer.Exit(2)
            sys.stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")
        return

    if action == HookAction.PRE_INVOCATION:
        raw = sys.stdin.read().strip()
        payload = json.loads(raw) if raw else {}
        text = _render_checklists()
        if not text:
            if agent == HookAgent.ANTIGRAVITY:
                sys.stdout.write("{}\n")
            return
        msg = f"Self-check your changes against these engineering checklists before finishing:\n\n{text}"
        if agent == HookAgent.ANTIGRAVITY:
            if payload.get("invocationNum", 1) == 1 and payload.get("workspacePaths"):
                sys.stdout.write(json.dumps({"injectSteps": [{"ephemeralMessage": msg}]}) + "\n")
            else:
                sys.stdout.write("{}\n")
        else:
            sys.stdout.write(msg + "\n")
        return

    verb = "Installed" if action == HookAction.INSTALL else "Uninstalled"

    if agent == HookAgent.GIT:
        if local:
            dest = Path.cwd() / ".git/hooks/pre-commit"
            if action == HookAction.UNINSTALL:
                dest.unlink(missing_ok=True)
                typer.echo(f"Removed {dest}")
            else:
                dest.unlink(missing_ok=True)
                dest.symlink_to(REPO_DIR / "hooks/pre-commit")
                typer.echo(f"Linked {dest} -> {REPO_DIR / 'hooks/pre-commit'}")
        elif action == HookAction.UNINSTALL:
            subprocess.run(["git", "config", "--global", "--unset", "core.hooksPath"], check=False)
            typer.echo("Unset global git core.hooksPath")
        else:
            subprocess.run(
                ["git", "config", "--global", "core.hooksPath", str(REPO_DIR / "hooks")], check=True
            )
            typer.echo(f"Set global git core.hooksPath -> {REPO_DIR / 'hooks'}")
        return

    if agent == HookAgent.ANTIGRAVITY:
        if local:
            hooks_file = Path.cwd() / ".agents/hooks.json"
        else:
            hooks_file = Path.home() / ".gemini/config/hooks.json"
        hooks_file.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, object] = json.loads(hooks_file.read_text()) if hooks_file.exists() else {}
        if action == HookAction.UNINSTALL:
            data.pop("lints", None)
        else:
            data["lints"] = {
                "PreInvocation": [
                    {
                        "type": "command",
                        "command": f"{bin_cmd} hook pre-invocation --agent antigravity",
                        "timeout": 10,
                    }
                ],
                "Stop": [
                    {
                        "type": "command",
                        "command": f"{bin_cmd} hook stop --agent antigravity",
                        "timeout": 20,
                    }
                ],
            }
        hooks_file.write_text(json.dumps(data, indent=2) + "\n")
        typer.echo(f"{verb} Antigravity hooks in {hooks_file}")
        return

    start_entry = {
        "hooks": [
            {"type": "command", "command": f"{bin_cmd} hook pre-invocation --agent {agent.value}"}
        ]
    }
    stop_entry = {
        "hooks": [
            {
                "type": "command",
                "command": f"{bin_cmd} hook stop --agent {agent.value}",
                "timeout": 20,
            }
        ]
    }

    if agent == HookAgent.CLAUDE:
        cfg_file = (
            Path.cwd() / ".claude/settings.json" if local else Path.home() / ".claude/settings.json"
        )
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        root: dict[str, object] = json.loads(cfg_file.read_text()) if cfg_file.exists() else {}
        hooks_map = root.setdefault("hooks", {})
        if isinstance(hooks_map, dict):
            for ev, entry in (("UserPromptSubmit", start_entry), ("Stop", stop_entry)):
                cur_list = hooks_map.get(ev, [])
                cleaned = _filter_claude_codex_entries(
                    cur_list if isinstance(cur_list, list) else [], bin_cmd
                )
                hooks_map[ev] = [*cleaned, entry] if action == HookAction.INSTALL else cleaned
        cfg_file.write_text(json.dumps(root, indent=2) + "\n")
        typer.echo(f"{verb} Claude Code hooks in {cfg_file}")
        return

    # HookAgent.CODEX
    cfg_file = Path.cwd() / ".codex/hooks.json" if local else Path.home() / ".codex/hooks.json"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    codex_root: dict[str, object] = json.loads(cfg_file.read_text()) if cfg_file.exists() else {}
    for ev, entry in (("UserPromptSubmit", start_entry), ("Stop", stop_entry)):
        cur_list = codex_root.get(ev, [])
        cleaned = _filter_claude_codex_entries(
            cur_list if isinstance(cur_list, list) else [], bin_cmd
        )
        codex_root[ev] = [*cleaned, entry] if action == HookAction.INSTALL else cleaned
    cfg_file.write_text(json.dumps(codex_root, indent=2) + "\n")
    typer.echo(f"{verb} Codex hooks in {cfg_file}")


@app.command()
def bootstrap(with_git_hook: bool = typer.Option(False, "--with-git-hook")) -> None:
    """Link central configs, install uv/oxlint tools, and start 60s auto-sync."""
    rich_path = _setup_path()
    build()
    for link, target_file in (
        (Path.home() / ".config/ruff/ruff.toml", RUFF_TOML),
        (Path.home() / "oxlint.config.ts", REPO_DIR / "oxlint.config.ts"),
    ):
        link.parent.mkdir(parents=True, exist_ok=True)
        link.unlink(missing_ok=True)
        link.symlink_to(target_file)
        typer.echo(f"Linked {link} -> {target_file}")

    subprocess.run(["uv", "tool", "install", "--force", "--editable", str(REPO_DIR)], check=True)
    if not shutil.which("ruff"):
        subprocess.run(["uv", "tool", "install", "ruff"], check=True)
    if not shutil.which("oxlint") and shutil.which("bun"):
        subprocess.run(["bun", "install", "-g", "oxlint"], check=True)
    if with_git_hook:
        subprocess.run(
            ["git", "config", "--global", "core.hooksPath", str(REPO_DIR / "hooks")], check=True
        )

    uv_bin = shutil.which("uv") or "uv"
    sync_cmd = [
        uv_bin,
        "run",
        "--quiet",
        "--project",
        str(REPO_DIR),
        "lints",
        "sync",
        "--background",
    ]
    if platform.system() == "Darwin":
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLIST_PATH.write_bytes(
            plistlib.dumps(
                {
                    "Label": "com.lints.sync",
                    "ProgramArguments": sync_cmd,
                    "StartInterval": 60,
                    "RunAtLoad": True,
                    "EnvironmentVariables": {"PATH": rich_path, "HOME": str(Path.home())},
                }
            )
        )
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST_PATH)],
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST_PATH)], check=False
        )
    elif shutil.which("crontab"):
        cur = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False
        ).stdout.splitlines()
        lines = [ln for ln in cur if CRON_TAG not in ln]
        lines.append(f"* * * * * PATH={rich_path} {' '.join(sync_cmd)} {CRON_TAG}")
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
    typer.echo("Bootstrap complete!")


if __name__ == "__main__":
    app()
