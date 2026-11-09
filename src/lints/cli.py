"""CLI entrypoint for `lints`."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from lints.config import (
    CONFIG_TOML,
    RuleSpec,
    build_artifacts,
    discover_rules,
    load_toml_config,
    set_lints_setting,
    set_rule_enabled,
)
from lints.env import ensure_rich_path, get_editor
from lints.runner import (
    explain_rule,
    resolve_oxlint_cmd,
    resolve_ruff_cmd,
    run_cmd,
    run_lint,
    run_python_ast_rules,
    run_rule_tests,
    scaffold_new_rule,
)
from lints.sync import (
    daemon_tick,
    install_daemon,
    print_daemon_status,
    run_bootstrap,
    run_push,
    run_status,
    run_update,
    scan_scattered_configs,
    uninstall_daemon,
)


def _match_rules(query: str) -> list[RuleSpec]:
    return [r for r in discover_rules() if query in {r.rule_id, r.name}]


def _toggle_rule(query: str, *, enabled: bool, local: bool) -> int:
    matches = _match_rules(query)
    if not matches:
        print(f"error: no rule matching `{query}` (run `lints list`)", file=sys.stderr)
        return 1
    if len(matches) > 1 and "/" not in query:
        ids = ", ".join(m.rule_id for m in matches)
        print(
            f"error: `{query}` matches multiple rules ({ids}); specify `<ts|py>/<name>`",
            file=sys.stderr,
        )
        return 1

    target_toml = Path.cwd() / "lints.toml" if local else CONFIG_TOML
    for spec in matches:
        set_rule_enabled(spec.lang, spec.name, enabled, target_toml)
        state = "enabled" if enabled else "disabled"
        print(f"{state}: {spec.rule_id} (in {target_toml})")

    if not local:
        build_artifacts()
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    cfg = load_toml_config(CONFIG_TOML)
    rules = discover_rules(cfg)
    print(f"Target dir: {cfg.target}   Rules dir: {cfg.rules_dir}   Config: {CONFIG_TOML}\n")
    for spec in rules:
        state = "on " if spec.enabled else "off"
        kind = "ast" if (spec.custom_ts_file or spec.custom_py_file) else "cfg"
        print(f"  [{state}] {spec.rule_id:<34} ({kind})  {spec.summary}")
    return 0


def cmd_target(args: argparse.Namespace) -> int:
    target_toml = Path.cwd() / "lints.toml" if args.local else CONFIG_TOML
    if not args.directory:
        cfg = load_toml_config(target_toml if target_toml.exists() else CONFIG_TOML)
        print(cfg.target)
        return 0
    set_lints_setting("target", args.directory, target_toml)
    print(f"Set default lint target = {args.directory!r} in {target_toml}")
    return 0


def cmd_rules_dir(args: argparse.Namespace) -> int:
    set_lints_setting("rules_dir", args.directory, CONFIG_TOML)
    build_artifacts()
    print(f"Set rules_dir = {args.directory!r} in {CONFIG_TOML} and rebuilt configs.")
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    if args.query == "config" or args.query is None:
        target = CONFIG_TOML
    else:
        matches = _match_rules(args.query)
        if not matches:
            print(f"error: unknown rule `{args.query}`", file=sys.stderr)
            return 1
        spec = matches[0]
        target = spec.custom_ts_file or spec.custom_py_file or (spec.folder / "rule.json")

    editor = get_editor()
    if not editor:
        print(target)
        return 0
    return subprocess.run([*editor.split(), str(target)], check=False).returncode


def cmd_ruff_check(args: argparse.Namespace) -> int:
    targets = args.paths or ["."]
    ruff = resolve_ruff_cmd()
    rc = run_cmd(
        [*ruff, "check", "--config", str(CONFIG_TOML.parent / "ruff.toml"), *targets]
    ).returncode
    py_files = [Path(p) for p in targets if Path(p).is_file()]
    ast_rc = run_python_ast_rules(py_files, discover_rules())
    return 1 if (rc != 0 or ast_rc != 0) else 0


def cmd_oxlint_check(args: argparse.Namespace) -> int:
    oxlint = resolve_oxlint_cmd()
    if oxlint is None:
        print("error: oxlint not found", file=sys.stderr)
        return 1
    targets = args.paths or ["."]
    return run_cmd(
        [*oxlint, "-c", str(CONFIG_TOML.parent / "oxlint.config.ts"), *targets]
    ).returncode


def cmd_daemon(args: argparse.Namespace) -> int:
    if args.action == "tick":
        return daemon_tick()
    if args.action == "install":
        install_daemon()
        return 0
    if args.action == "uninstall":
        uninstall_daemon()
        return 0
    print_daemon_status()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lints",
        description="Self-contained Ruff + Oxlint rules controlled via config.toml.",
    )
    sub = parser.add_subparsers(dest="command")

    p_lint = sub.add_parser(
        "lint", aliases=["check"], help="Lint configured target directory (or explicit paths)"
    )
    p_lint.add_argument(
        "paths", nargs="*", help="Optional files or folders (defaults to `target` in config.toml)"
    )
    p_lint.set_defaults(func=lambda a: run_lint(a.paths, fix=False))

    p_fix = sub.add_parser("fix", help="Auto-fix & format Python and TypeScript files")
    p_fix.add_argument("paths", nargs="*", help="Optional files or folders")
    p_fix.set_defaults(func=lambda a: run_lint(a.paths, fix=True))

    p_list = sub.add_parser("list", help="List all self-contained rules and their enabled state")
    p_list.set_defaults(func=cmd_list)

    p_en = sub.add_parser(
        "enable", help="Enable a rule in config.toml (or ./lints.toml with --local)"
    )
    p_en.add_argument("rule", help="Rule ID, e.g. `ts/no-nullish-coalescing`")
    p_en.add_argument(
        "--local", action="store_true", help="Write override to ./lints.toml in current project"
    )
    p_en.set_defaults(func=lambda a: _toggle_rule(a.rule, enabled=True, local=a.local))

    p_dis = sub.add_parser(
        "disable", help="Disable a rule in config.toml (or ./lints.toml with --local)"
    )
    p_dis.add_argument("rule", help="Rule ID, e.g. `ts/no-default-export`")
    p_dis.add_argument(
        "--local", action="store_true", help="Write override to ./lints.toml in current project"
    )
    p_dis.set_defaults(func=lambda a: _toggle_rule(a.rule, enabled=False, local=a.local))

    p_new = sub.add_parser("new", help="Scaffold a new self-contained rule folder + tests")
    p_new.add_argument("rule", help="`<ts|py>/<rule-name>`, e.g. `ts/no-date-now`")
    p_new.add_argument("--summary", default="", help="One-line rule summary")
    p_new.set_defaults(func=lambda a: scaffold_new_rule(a.rule, a.summary))

    p_test = sub.add_parser("test", help="Run hermetic invalid/valid fixture tests for each rule")
    p_test.add_argument(
        "rule", nargs="?", default=None, help="Optional rule ID or `ts` / `py` filter"
    )
    p_test.set_defaults(func=lambda a: run_rule_tests(a.rule))

    p_exp = sub.add_parser("explain", help="Print a rule's README + valid/invalid examples")
    p_exp.add_argument("rule", help="Rule ID or code, e.g. `ts/no-type-assertion` or `PY001`")
    p_exp.set_defaults(func=lambda a: explain_rule(a.rule))

    p_tgt = sub.add_parser("target", help="Get or set the default folder linted by `lints lint`")
    p_tgt.add_argument(
        "directory", nargs="?", default=None, help="Directory path (e.g. `src` or `~/code/app`)"
    )
    p_tgt.add_argument(
        "--local", action="store_true", help="Save target in ./lints.toml for current project"
    )
    p_tgt.set_defaults(func=cmd_target)

    p_rdir = sub.add_parser(
        "rules-dir", help="Set the folder directory containing rule definitions"
    )
    p_rdir.add_argument("directory", help="Path to rules directory")
    p_rdir.set_defaults(func=cmd_rules_dir)

    p_build = sub.add_parser("build", help="Compile enabled rules into ruff.toml and .generated/")
    p_build.set_defaults(func=lambda _a: build_artifacts() or 0)

    p_edit = sub.add_parser("edit", help="Open config.toml or a specific rule in $EDITOR")
    p_edit.add_argument(
        "query", nargs="?", default="config", help="`config` (default) or a rule ID"
    )
    p_edit.set_defaults(func=cmd_edit)

    p_push = sub.add_parser("push", help="Run rule tests, build configs, commit, rebase, and push")
    p_push.add_argument("message", nargs="*", help="Optional commit message")
    p_push.add_argument("--force", action="store_true", help="Skip rule tests before pushing")
    p_push.set_defaults(func=lambda a: run_push(a.message, force=a.force))

    p_upd = sub.add_parser("update", aliases=["pull", "sync"], help="Pull latest rules from GitHub")
    p_upd.add_argument("--tools", action="store_true", help="Also upgrade ruff & oxlint binaries")
    p_upd.set_defaults(func=lambda a: run_update(upgrade_tools=a.tools))

    p_scan = sub.add_parser("scan", help="Find scattered per-project ruff/oxlint configs")
    p_scan.add_argument("dir", nargs="?", default=".", help="Directory to scan")
    p_scan.set_defaults(func=lambda a: scan_scattered_configs(a.dir))

    p_stat = sub.add_parser("status", help="Show git, symlink, tool, and 60s sync status")
    p_stat.set_defaults(func=lambda _a: run_status())

    p_boot = sub.add_parser("bootstrap", help="Install uv CLI, symlinks, linters, and 60s sync")
    p_boot.add_argument(
        "--no-tools", action="store_true", help="Skip installing ruff/oxlint binaries"
    )
    p_boot.add_argument("--no-daemon", action="store_true", help="Skip installing 60s sync timer")
    p_boot.add_argument(
        "--with-git-hook", action="store_true", help="Enable global Git pre-commit hook"
    )
    p_boot.set_defaults(
        func=lambda a: run_bootstrap(
            no_tools=a.no_tools,
            no_daemon=a.no_daemon,
            with_git_hook=a.with_git_hook,
        )
    )

    p_daemon = sub.add_parser("daemon", help="Manage the 60-second background sync timer")
    p_daemon.add_argument("action", choices=["install", "uninstall", "status", "tick"])
    p_daemon.set_defaults(func=cmd_daemon)

    p_rc = sub.add_parser("ruff-check")
    p_rc.add_argument("paths", nargs="*")
    p_rc.set_defaults(func=cmd_ruff_check)

    p_oc = sub.add_parser("oxlint-check")
    p_oc.add_argument("paths", nargs="*")
    p_oc.set_defaults(func=cmd_oxlint_check)

    return parser


def main() -> int:
    ensure_rich_path()
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        return run_lint([], fix=False)
    func = args.__dict__.get("func")
    if callable(func):
        return int(func(args))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
