---
name: lints
description: >-
  Run, configure, author, and sync centralised Ruff and Oxlint rules, model
  self-check lists, and pre-turn-end agent hooks via the `lints` CLI. Use when
  bootstrapping linting on a machine or repo, fixing `lints` violations,
  reviewing code/PR checklists, installing pre-turn-end hooks, or proposing new
  self-contained `.ts`/`.py` lint rules.
---

# `lints` Skill

## 1. Install / Bootstrap (If Missing)

If `command -v lints` fails, bootstrap from GitHub:

```sh
git clone https://github.com/ivanleomk/lints.git ~/.config/lints
~/.config/lints/bin/lints bootstrap
```

Optional pre-turn-end & checklist hook (`--local` scopes to the current repo):

```sh
lints hook install --agent <antigravity|claude|codex|git> [--local]
```

## 2. Lint, Fix & Self-Review Code

Run `lints` before finishing code changes or opening a PR:

```sh
lints lint [paths...]          # Run Ruff + Python AST + Oxlint (defaults to `target` in config.toml)
lints fix [paths...]           # Auto-fix and format Python + TypeScript
lints explain <rule-id>        # View README + invalid/valid test fixtures for any failing rule
lints checklist                # Print active code-quality & pr-quality checklists
```

## 3. Configure Per-Project or Globally

Global defaults live in `~/.config/lints/config.toml`; pass `--local` to write repo-scoped overrides to `./lints.toml`:

```sh
lints list
lints target src --local
lints disable ts/no-default-export --local
lints enable ts/no-nullish-coalescing --local
```

## 4. Create & Sync Rules Across Machines

Every rule is a self-contained folder under `rules/<ts|py>/<name>/` (`rule.json`, `README.md`, optional `rule.ts`/`rule.py`, and `tests/{invalid,valid}*`):

```sh
lints sync                                      # Pull latest merged `main` & rebuild configs
lints new ts/no-date-now --summary "Reason"     # Scaffold rule folder + fixtures
lints test ts/no-date-now                       # Verify invalid fails & valid passes in isolation
lints propose "feat: add ts/no-date-now"        # Run all tests -> push branch -> open/update PR
lints merge                                     # Squash-merge PR and sync `main`
```
