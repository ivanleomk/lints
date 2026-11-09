"""GitHub sync, 60-second background daemon, machine bootstrap, and status."""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import socket
import subprocess
import sys

from lints.config import GENERATED_RUFF_TOML, REPO_DIR, build_artifacts
from lints.env import ensure_rich_path, non_interactive_git_env, path_entries
from lints.runner import SKIP_DIRS, resolve_oxlint_cmd, resolve_ruff_cmd, run_rule_tests

CACHE_DIR = Path.home() / ".cache" / "lints"
STATUS_FILE = CACHE_DIR / "status.json"
LOCK_FILE = CACHE_DIR / "sync.lock"
LOG_FILE = CACHE_DIR / "sync.log"

LAUNCHD_LABEL = "com.lints.sync"
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_SERVICE = SYSTEMD_DIR / "lints-sync.service"
SYSTEMD_TIMER = SYSTEMD_DIR / "lints-sync.timer"
CRON_MARKER = "# lints-auto-sync"


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=capture,
        timeout=timeout,
        env=env,
    )


def managed_symlinks() -> list[tuple[Path, Path]]:
    home = Path.home()
    return [
        (home / ".config" / "ruff" / "ruff.toml", GENERATED_RUFF_TOML),
        (home / "oxlint.config.ts", REPO_DIR / "oxlint.config.ts"),
    ]


def ensure_symlink(link_path: Path, target_path: Path) -> str:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink():
        if link_path.resolve() == target_path.resolve():
            return "unchanged"
        link_path.unlink()
    elif link_path.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
        backup = link_path.with_name(f"{link_path.name}.bak.{stamp}")
        link_path.rename(backup)
        print(f"  backed up existing {link_path} -> {backup}")
    link_path.symlink_to(target_path)
    return "linked"


def current_branch() -> str:
    res = _run(["git", "symbolic-ref", "--short", "HEAD"], cwd=REPO_DIR, capture=True)
    return res.stdout.strip() or "main"


def has_remote_origin() -> bool:
    res = _run(["git", "remote", "get-url", "origin"], cwd=REPO_DIR, capture=True)
    return res.returncode == 0 and bool(res.stdout.strip())


def git_in_rebase_or_merge() -> bool:
    res = _run(["git", "rev-parse", "--git-dir"], cwd=REPO_DIR, capture=True)
    if res.returncode != 0:
        return False
    git_dir = (REPO_DIR / res.stdout.strip()).resolve()
    return any(
        (git_dir / marker).exists() for marker in ("rebase-merge", "rebase-apply", "MERGE_HEAD")
    )


def sync_pull(*, quiet: bool = False) -> tuple[bool, str]:
    if not has_remote_origin():
        return True, "no git remote `origin` configured"
    if git_in_rebase_or_merge():
        return False, "skipped: git rebase/merge in progress"

    branch = current_branch()
    env = non_interactive_git_env()

    try:
        fetch = _run(
            ["git", "fetch", "--quiet", "origin", branch],
            cwd=REPO_DIR,
            capture=True,
            timeout=15,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, "fetch timed out"

    if fetch.returncode != 0:
        lines = (fetch.stderr or fetch.stdout).strip().splitlines()
        msg = lines[0] if lines else "git fetch failed"
        return False, msg

    anc = _run(
        ["git", "merge-base", "--is-ancestor", f"origin/{branch}", "HEAD"],
        cwd=REPO_DIR,
        capture=True,
    )
    if anc.returncode == 0:
        return True, "already up to date"

    if not quiet:
        print(f"==> Pulling latest lint rules from origin/{branch}...")

    rebase = _run(
        ["git", "rebase", "--autostash", f"origin/{branch}"],
        cwd=REPO_DIR,
        capture=True,
        timeout=30,
        env=env,
    )
    if rebase.returncode != 0:
        _run(["git", "rebase", "--abort"], cwd=REPO_DIR, capture=True)
        err = (rebase.stderr or rebase.stdout).strip()
        return False, f"rebase conflict aborted: {err}"

    build_artifacts()
    sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_DIR, capture=True).stdout.strip()
    return True, f"updated to {sha}"


def install_tools(upgrade: bool = False) -> None:
    if shutil.which("uv"):
        editable_cmd = ["uv", "tool", "install", "--force", "--editable", str(REPO_DIR)]
        print(f"==> {' '.join(editable_cmd)}")
        _run(editable_cmd)

        if upgrade or not shutil.which("ruff"):
            ruff_cmd = ["uv", "tool", "install", *(["--upgrade"] if upgrade else []), "ruff"]
            print(f"==> {' '.join(ruff_cmd)}")
            _run(ruff_cmd)
    else:
        local_bin = Path.home() / ".local" / "bin" / "lints"
        ensure_symlink(local_bin, REPO_DIR / "bin" / "lints")

    if upgrade or not shutil.which("oxlint"):
        pkg = "oxlint@latest" if upgrade else "oxlint"
        if shutil.which("bun"):
            cmd = ["bun", "install", "-g", pkg]
            print(f"==> {' '.join(cmd)}")
            _run(cmd)
        elif shutil.which("npm"):
            cmd = ["npm", "install", "-g", pkg]
            print(f"==> {' '.join(cmd)}")
            _run(cmd)


def run_update(*, upgrade_tools: bool = False) -> int:
    ok, msg = sync_pull(quiet=False)
    if not ok:
        print(f"error: {msg}", file=sys.stderr)
        return 1
    build_artifacts()
    print(f"Sync: {msg}")
    if upgrade_tools:
        install_tools(upgrade=True)
    return 0


def run_push(message_parts: list[str], *, force: bool = False) -> int:
    build_artifacts()
    if not force:
        print("==> Running hermetic rule tests before push...")
        if run_rule_tests(None) != 0:
            return 1

    status = _run(["git", "status", "--porcelain"], cwd=REPO_DIR, capture=True).stdout.strip()
    if status:
        _run(["git", "add", "-A"], cwd=REPO_DIR)
        msg = " ".join(message_parts).strip()
        if not msg:
            host = socket.gethostname().split(".")[0]
            msg = f"chore: update lints ({host})"
        commit_res = _run(["git", "commit", "-m", msg], cwd=REPO_DIR)
        if commit_res.returncode != 0:
            return commit_res.returncode
    else:
        print("Working tree clean; checking remote sync...")

    if not has_remote_origin():
        print("error: no `origin` remote configured in repo.", file=sys.stderr)
        return 1

    branch = current_branch()
    ok, pull_msg = sync_pull(quiet=False)
    if not ok:
        print(f"error pulling before push: {pull_msg}", file=sys.stderr)
        return 1

    print(f"==> Pushing to origin/{branch}...")
    push_res = _run(["git", "push", "-u", "origin", branch], cwd=REPO_DIR)
    if push_res.returncode == 0:
        print("Pushed! Other machines running the `lints` daemon will sync within 60s.")
    return push_res.returncode


def write_tick_status(ok: bool, detail: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_DIR, capture=True).stdout.strip()
    payload = {
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
        "ok": ok,
        "detail": detail,
        "commit": sha,
    }
    STATUS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def daemon_tick() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock_fh:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        ok, detail = sync_pull(quiet=True)
        write_tick_status(ok, detail)
        return 0 if ok else 1


def _daemon_program_args() -> list[str]:
    uv_bin = shutil.which("uv")
    if uv_bin:
        return [uv_bin, "run", "--quiet", "--project", str(REPO_DIR), "lints", "daemon", "tick"]
    return [str(REPO_DIR / "bin" / "lints"), "daemon", "tick"]


def install_daemon() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rich_path = ensure_rich_path()
    prog_args = _daemon_program_args()
    sys_name = platform.system()

    if sys_name == "Darwin":
        LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
        plist_data = {
            "Label": LAUNCHD_LABEL,
            "ProgramArguments": prog_args,
            "StartInterval": 60,
            "RunAtLoad": True,
            "EnvironmentVariables": {
                "PATH": rich_path,
                "HOME": str(Path.home()),
            },
            "StandardOutPath": str(LOG_FILE),
            "StandardErrorPath": str(LOG_FILE),
        }
        with LAUNCHD_PLIST.open("wb") as fh:
            plistlib.dump(plist_data, fh)

        uid = os.getuid()
        _run(["launchctl", "bootout", f"gui/{uid}", str(LAUNCHD_PLIST)], capture=True)
        boot = _run(["launchctl", "bootstrap", f"gui/{uid}", str(LAUNCHD_PLIST)], capture=True)
        if boot.returncode != 0:
            _run(["launchctl", "load", "-w", str(LAUNCHD_PLIST)])
        print(f"Installed 60s macOS launchd sync agent ({LAUNCHD_PLIST})")
        return

    if shutil.which("systemctl"):
        check_user = _run(["systemctl", "--user", "status"], capture=True)
        if check_user.returncode in (0, 3):
            SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
            joined_prog = " ".join(prog_args)
            SYSTEMD_SERVICE.write_text(
                "[Unit]\n"
                "Description=Sync central lints repository\n\n"
                "[Service]\n"
                "Type=oneshot\n"
                f'Environment="PATH={rich_path}"\n'
                f"ExecStart={joined_prog}\n",
                encoding="utf-8",
            )
            SYSTEMD_TIMER.write_text(
                "[Unit]\n"
                "Description=Run lints sync every minute\n\n"
                "[Timer]\n"
                "OnBootSec=15s\n"
                "OnUnitActiveSec=60s\n"
                "AccuracySec=5s\n\n"
                "[Install]\n"
                "WantedBy=timers.target\n",
                encoding="utf-8",
            )
            _run(["systemctl", "--user", "daemon-reload"])
            _run(["systemctl", "--user", "enable", "--now", "lints-sync.timer"])
            print(f"Installed 60s systemd user timer ({SYSTEMD_TIMER})")
            return

    if shutil.which("crontab"):
        existing = _run(["crontab", "-l"], capture=True)
        raw_lines = existing.stdout.splitlines() if existing.returncode == 0 else []
        lines = [ln for ln in raw_lines if CRON_MARKER not in ln]
        joined_prog = " ".join(prog_args)
        lines.append(f"* * * * * PATH={rich_path} {joined_prog} {CRON_MARKER}")
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=False)
        print("Installed 60s crontab auto-sync entry.")
        return

    print("warning: could not configure background timer automatically on this OS.")


def uninstall_daemon() -> None:
    if platform.system() == "Darwin":
        if LAUNCHD_PLIST.exists():
            uid = os.getuid()
            _run(["launchctl", "bootout", f"gui/{uid}", str(LAUNCHD_PLIST)], capture=True)
            LAUNCHD_PLIST.unlink(missing_ok=True)
            print("Removed macOS launchd sync agent.")
        else:
            print("macOS launchd agent is not installed.")
        return

    if SYSTEMD_TIMER.exists() or SYSTEMD_SERVICE.exists():
        _run(["systemctl", "--user", "disable", "--now", "lints-sync.timer"])
        SYSTEMD_TIMER.unlink(missing_ok=True)
        SYSTEMD_SERVICE.unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"])
        print("Removed systemd user timer.")

    if shutil.which("crontab"):
        existing = _run(["crontab", "-l"], capture=True)
        if existing.returncode == 0 and CRON_MARKER in existing.stdout:
            kept = [ln for ln in existing.stdout.splitlines() if CRON_MARKER not in ln]
            payload = ("\n".join(kept) + "\n") if kept else ""
            subprocess.run(["crontab", "-"], input=payload, text=True, check=False)
            print("Removed crontab auto-sync entry.")


def daemon_is_installed() -> tuple[bool, str]:
    if platform.system() == "Darwin":
        return LAUNCHD_PLIST.exists(), f"launchd ({LAUNCHD_PLIST})"
    if SYSTEMD_TIMER.exists():
        return True, f"systemd ({SYSTEMD_TIMER})"
    if shutil.which("crontab"):
        existing = _run(["crontab", "-l"], capture=True)
        if existing.returncode == 0 and CRON_MARKER in existing.stdout:
            return True, "crontab (* * * * *)"
    return False, "not installed"


def print_daemon_status() -> None:
    installed, kind = daemon_is_installed()
    state_label = "installed" if installed else "not installed"
    print(f"Daemon:    {state_label} — {kind}")
    if STATUS_FILE.exists():
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        ok_label = "ok" if data.get("ok") else "error"
        print(
            f"Last tick: {data.get('timestamp')} [{ok_label}] "
            f"({data.get('detail')}, commit {data.get('commit')})"
        )
    else:
        print("Last tick: none recorded yet")


def run_bootstrap(*, no_tools: bool, no_daemon: bool, with_git_hook: bool) -> int:
    build_artifacts()

    # Clean up legacy ~/oxlint.config.mts symlink if it pointed into REPO_DIR
    legacy_mts = Path.home() / "oxlint.config.mts"
    if legacy_mts.is_symlink() and REPO_DIR in legacy_mts.resolve().parents:
        legacy_mts.unlink()

    print(f"==> Linking central configs from {REPO_DIR}")
    for link_path, target_path in managed_symlinks():
        state = ensure_symlink(link_path, target_path)
        print(f"  {link_path} -> {target_path} ({state})")

    if not no_tools:
        install_tools(upgrade=False)

    if with_git_hook:
        hooks_dir = REPO_DIR / "hooks"
        _run(["git", "config", "--global", "core.hooksPath", str(hooks_dir)])
        print(f"==> Configured global Git hooksPath -> {hooks_dir}")

    if not no_daemon:
        install_daemon()
        daemon_tick()

    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in path_entries():
        print(f"\nnote: ensure `{local_bin}` is in your shell PATH.")
    print("\nBootstrap complete! Run `lints lint` or `lints status` anytime.")
    return 0


def run_status() -> int:
    branch = current_branch()
    sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_DIR, capture=True).stdout.strip()
    dirty = bool(_run(["git", "status", "--porcelain"], cwd=REPO_DIR, capture=True).stdout.strip())
    remote_url = _run(
        ["git", "remote", "get-url", "origin"], cwd=REPO_DIR, capture=True
    ).stdout.strip()

    print(f"Repo:      {REPO_DIR}")
    print(f"Config:    {REPO_DIR / 'config.toml'}")
    print(f"Git:       {branch} @ {sha or 'uncommitted'} ({'dirty' if dirty else 'clean'})")
    print(f"Remote:    {remote_url or 'none'}")

    print("\nSymlinks:")
    for link_path, target_path in managed_symlinks():
        ok = link_path.is_symlink() and link_path.resolve() == target_path.resolve()
        marker = "ok" if ok else "not linked"
        print(f"  [{marker}] {link_path} -> {target_path}")

    ruff_cmd = " ".join(resolve_ruff_cmd())
    ox_resolved = resolve_oxlint_cmd()
    oxlint_cmd = " ".join(ox_resolved) if ox_resolved else "missing"
    print("\nLinters:")
    print(f"  ruff:    {ruff_cmd}")
    print(f"  oxlint:  {oxlint_cmd}")

    print()
    print_daemon_status()
    return 0


def scan_scattered_configs(raw_dir: str) -> int:
    root_dir = Path(raw_dir).expanduser().resolve()
    config_names = {
        "ruff.toml",
        ".ruff.toml",
        ".oxlintrc.json",
        ".oxlintrc.jsonc",
        "oxlint.config.ts",
        "oxlint.config.mts",
    }
    found: list[Path] = []
    for cur_root, dirs, files in os.walk(root_dir):
        cur_path = Path(cur_root)
        if cur_path == REPO_DIR or REPO_DIR in cur_path.parents:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            fpath = cur_path / fname
            if fname in config_names:
                found.append(fpath)
            elif fname == "pyproject.toml":
                try:
                    if "[tool.ruff" in fpath.read_text(encoding="utf-8", errors="ignore"):
                        found.append(fpath)
                except OSError:
                    pass

    if not found:
        print(f"No project-specific ruff/oxlint configs found under {root_dir}")
        return 0

    print(f"Found {len(found)} local linter config(s) under {root_dir}:")
    for p in sorted(found):
        print(f"  - {p}")
    return 0
