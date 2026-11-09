"""Configuration (`config.toml`), rule discovery, and generated config compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import tomllib

REPO_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_TOML = REPO_DIR / "config.toml"
GENERATED_DIR = REPO_DIR / ".generated"
GENERATED_OXLINT_CONFIG = GENERATED_DIR / "oxlint-config.json"
GENERATED_OXLINT_PLUGIN = GENERATED_DIR / "oxlint-plugin.ts"
GENERATED_RUFF_TOML = REPO_DIR / "ruff.toml"


@dataclass
class LintsConfig:
    target: str = "."
    rules_dir: str = "rules"
    ts_enabled: dict[str, bool] = field(default_factory=dict)
    py_enabled: dict[str, bool] = field(default_factory=dict)


@dataclass
class RuleSpec:
    lang: str
    name: str
    folder: Path
    enabled: bool
    summary: str
    meta: dict[str, object]

    @property
    def rule_id(self) -> str:
        return f"{self.lang}/{self.name}"

    @property
    def custom_ts_file(self) -> Path | None:
        candidate = self.folder / "rule.ts"
        if candidate.exists():
            return candidate
        return None

    @property
    def custom_py_file(self) -> Path | None:
        candidate = self.folder / "rule.py"
        if candidate.exists():
            return candidate
        return None


def load_toml_config(path: Path = CONFIG_TOML) -> LintsConfig:
    if not path.exists():
        return LintsConfig()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    lints_sec = raw.get("lints")
    target = "."
    rules_dir = "rules"
    if isinstance(lints_sec, dict):
        raw_target = lints_sec.get("target")
        if isinstance(raw_target, str):
            target = raw_target
        raw_rules_dir = lints_sec.get("rules_dir")
        if isinstance(raw_rules_dir, str):
            rules_dir = raw_rules_dir

    ts_sec = raw.get("ts")
    ts_enabled: dict[str, bool] = {}
    if isinstance(ts_sec, dict):
        for key, val in ts_sec.items():
            if isinstance(val, bool):
                ts_enabled[str(key)] = val

    py_sec = raw.get("py")
    py_enabled: dict[str, bool] = {}
    if isinstance(py_sec, dict):
        for key, val in py_sec.items():
            if isinstance(val, bool):
                py_enabled[str(key)] = val

    return LintsConfig(
        target=target,
        rules_dir=rules_dir,
        ts_enabled=ts_enabled,
        py_enabled=py_enabled,
    )


def find_local_project_config(start: Path) -> Path | None:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    while True:
        for candidate_name in ("lints.toml", ".lints.toml"):
            candidate = cur / candidate_name
            if candidate.exists() and candidate.resolve() != CONFIG_TOML.resolve():
                return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent


def resolve_effective_config(cwd: Path) -> tuple[LintsConfig, Path | None]:
    base = load_toml_config(CONFIG_TOML)
    local_path = find_local_project_config(cwd)
    if local_path is None:
        return base, None

    local_cfg = load_toml_config(local_path)
    merged_ts = {**base.ts_enabled, **local_cfg.ts_enabled}
    merged_py = {**base.py_enabled, **local_cfg.py_enabled}
    return (
        LintsConfig(
            target=local_cfg.target,
            rules_dir=base.rules_dir,
            ts_enabled=merged_ts,
            py_enabled=merged_py,
        ),
        local_path,
    )


def resolve_rules_root(cfg: LintsConfig) -> Path:
    raw = Path(cfg.rules_dir).expanduser()
    if raw.is_absolute():
        return raw
    return (REPO_DIR / raw).resolve()


def discover_rules(cfg: LintsConfig | None = None) -> list[RuleSpec]:
    active_cfg = cfg if cfg is not None else load_toml_config()
    rules_root = resolve_rules_root(active_cfg)
    specs: list[RuleSpec] = []

    for lang, enabled_map in (("ts", active_cfg.ts_enabled), ("py", active_cfg.py_enabled)):
        lang_dir = rules_root / lang
        if not lang_dir.is_dir():
            continue
        for folder in sorted(lang_dir.iterdir()):
            rule_json = folder / "rule.json"
            if not folder.is_dir() or not rule_json.exists():
                continue
            meta = json.loads(rule_json.read_text(encoding="utf-8"))
            summary = str(meta.get("summary", ""))
            enabled = enabled_map.get(folder.name, True)
            specs.append(
                RuleSpec(
                    lang=lang,
                    name=folder.name,
                    folder=folder,
                    enabled=enabled,
                    summary=summary,
                    meta=meta,
                )
            )
    return specs


def update_toml_key_in_section(
    toml_path: Path,
    section: str,
    key: str,
    rendered_value: str,
) -> None:
    text = toml_path.read_text(encoding="utf-8") if toml_path.exists() else ""
    lines = text.splitlines()
    sec_header = f"[{section}]"
    in_section = False
    sec_end_idx = -1
    key_pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)([^#\n]*)(#.*)?$")

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section:
                sec_end_idx = idx
                break
            if stripped == sec_header:
                in_section = True
            continue

        if in_section:
            match = key_pattern.match(line)
            if match:
                suffix = f" {match.group(3).strip()}" if match.group(3) else ""
                lines[idx] = f"{match.group(1)}{rendered_value}{suffix}"
                toml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return

    new_line = f"{key} = {rendered_value}"
    if in_section:
        insert_at = sec_end_idx if sec_end_idx != -1 else len(lines)
        while insert_at > 0 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, new_line)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([sec_header, new_line])

    toml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_rule_enabled(lang: str, name: str, enabled: bool, toml_path: Path = CONFIG_TOML) -> None:
    rendered = "true" if enabled else "false"
    update_toml_key_in_section(toml_path, lang, name, rendered)


def set_lints_setting(key: str, value: str, toml_path: Path = CONFIG_TOML) -> None:
    escaped = json.dumps(value)
    update_toml_key_in_section(toml_path, "lints", key, escaped)


def _ident_for_index(idx: int) -> str:
    return f"rule_{idx}"


def build_artifacts(cfg: LintsConfig | None = None) -> None:
    active_cfg = cfg if cfg is not None else load_toml_config()
    rules = discover_rules(active_cfg)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Compile Oxlint custom plugin + config JSON
    plugins: list[str] = ["typescript", "unicorn", "import", "oxc"]
    oxlint_rules: dict[str, object] = {
        "eqeqeq": ["error", "smart"],
        "prefer-const": "error",
        "no-var": "error",
        "no-eval": "error",
        "no-implied-eval": "error",
        "no-empty": ["error", {"allowEmptyCatch": False}],
        "no-unused-vars": [
            "error",
            {
                "argsIgnorePattern": "^_",
                "varsIgnorePattern": "^_",
                "caughtErrorsIgnorePattern": "^_",
            },
        ],
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
    ts_imports: list[str] = []
    ts_rule_entries: list[str] = []

    custom_idx = 0
    for spec in rules:
        if spec.lang != "ts" or not spec.enabled:
            continue

        ox_meta = spec.meta.get("oxlint")
        if isinstance(ox_meta, dict):
            raw_plugins = ox_meta.get("plugins")
            if isinstance(raw_plugins, list):
                for p in raw_plugins:
                    if isinstance(p, str) and p not in plugins:
                        plugins.append(p)
            raw_rules = ox_meta.get("rules")
            if isinstance(raw_rules, dict):
                oxlint_rules.update(raw_rules)
            raw_overrides = ox_meta.get("overrides")
            if isinstance(raw_overrides, list):
                overrides.extend(ov for ov in raw_overrides if isinstance(ov, dict))

        ts_file = spec.custom_ts_file
        if ts_file is not None:
            ident = _ident_for_index(custom_idx)
            custom_idx += 1
            rel_import = Path("..") / ts_file.relative_to(REPO_DIR)
            ts_imports.append(f'import {{ rule as {ident} }} from "{rel_import.as_posix()}";')
            ts_rule_entries.append(f'    "{spec.name}": {ident},')
            default_sev = str(spec.meta.get("defaultSeverity", "error"))
            if default_sev != "off":
                oxlint_rules[f"lints/{spec.name}"] = default_sev

    has_custom_plugin = len(ts_rule_entries) > 0
    plugin_source = (
        "// Auto-generated by `lints build` — do not edit manually.\n"
        + ("\n".join(ts_imports) + "\n\n" if ts_imports else "")
        + "export default {\n"
        + '  meta: { name: "lints" },\n'
        + "  rules: {\n"
        + ("\n".join(ts_rule_entries) + "\n" if ts_rule_entries else "")
        + "  },\n"
        + "};\n"
    )
    GENERATED_OXLINT_PLUGIN.write_text(plugin_source, encoding="utf-8")

    oxlint_payload = {
        "plugins": plugins,
        "categories": {"correctness": "error", "suspicious": "warn"},
        "hasCustomPlugin": has_custom_plugin,
        "rules": oxlint_rules,
        "overrides": overrides,
        "ignorePatterns": [
            "dist/**",
            "build/**",
            ".next/**",
            "out/**",
            "coverage/**",
            "node_modules/**",
            "rules/**/tests/**",
        ],
    }
    GENERATED_OXLINT_CONFIG.write_text(
        json.dumps(oxlint_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    # 2. Compile root ruff.toml
    select_codes: list[str] = [
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
    ignore_codes: list[str] = ["E501", "B008", "RET504", "PTH123"]
    banned_api: dict[str, str] = {}
    per_file_ignores: dict[str, list[str]] = {}

    for spec in rules:
        if spec.lang != "py" or not spec.enabled:
            continue
        ruff_meta = spec.meta.get("ruff")
        if not isinstance(ruff_meta, dict):
            continue
        raw_sel = ruff_meta.get("select")
        if isinstance(raw_sel, list):
            for code in raw_sel:
                if isinstance(code, str) and code not in select_codes:
                    select_codes.append(code)
        raw_ign = ruff_meta.get("ignore")
        if isinstance(raw_ign, list):
            for code in raw_ign:
                if isinstance(code, str) and code not in ignore_codes:
                    ignore_codes.append(code)
        raw_ban = ruff_meta.get("bannedApi")
        if isinstance(raw_ban, dict):
            banned_api.update(
                {
                    api: msg
                    for api, msg in raw_ban.items()
                    if isinstance(api, str) and isinstance(msg, str)
                }
            )
        raw_pfi = ruff_meta.get("perFileIgnores")
        if isinstance(raw_pfi, dict):
            for pattern, codes in raw_pfi.items():
                if isinstance(pattern, str) and isinstance(codes, list):
                    bucket = per_file_ignores.setdefault(pattern, [])
                    for code in codes:
                        if isinstance(code, str) and code not in bucket:
                            bucket.append(code)

    ruff_lines = [
        "# Auto-generated by `lints build` from `config.toml` and `rules/py/*`.",
        "# Toggle rules via `config.toml` or `lints enable` / `lints disable`.",
        "#",
        "# Per-project override example:",
        '#   extend = "~/.config/ruff/ruff.toml"',
        "",
        "line-length = 100",
        'target-version = "py312"',
        "exclude = [",
        '  ".git",',
        '  ".venv",',
        '  "venv",',
        '  "__pycache__",',
        '  "node_modules",',
        '  "dist",',
        '  "build",',
        '  "rules/**/tests/**",',
        "]",
        "",
        "[lint]",
        f"select = {json.dumps(select_codes)}",
        f"ignore = {json.dumps(ignore_codes)}",
        "",
        "[lint.flake8-tidy-imports]",
        'ban-relative-imports = "parents"',
    ]

    if banned_api:
        ruff_lines.extend(["", "[lint.flake8-tidy-imports.banned-api]"])
        for api, msg in banned_api.items():
            ruff_lines.append(f"{json.dumps(api)} = {{ msg = {json.dumps(msg)} }}")

    if per_file_ignores:
        ruff_lines.extend(["", "[lint.per-file-ignores]"])
        for pattern, codes in per_file_ignores.items():
            ruff_lines.append(f"{json.dumps(pattern)} = {json.dumps(codes)}")

    ruff_lines.extend(
        [
            "",
            "[lint.isort]",
            "combine-as-imports = true",
            "force-sort-within-sections = true",
            "",
            "[format]",
            'quote-style = "double"',
            'indent-style = "space"',
            "",
        ]
    )
    GENERATED_RUFF_TOML.write_text("\n".join(ruff_lines), encoding="utf-8")
