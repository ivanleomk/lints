# `lints`

Centralised, self-contained **Ruff** + **Oxlint** lint rules and model self-check lists controlled via [`config.toml`](./config.toml), powered by `uv` + Typer + `.ts` plugins.

## Setup on Any Machine

```sh
git clone https://github.com/ivanleomk/lints.git ~/.config/lints
~/.config/lints/bin/lints bootstrap
```

Optional: register `lints` as a **pre-turn-end Antigravity lifecycle hook** (`~/.gemini/config/hooks.json` or `--local` for `.agents/hooks.json`):

```sh
lints hook install
```

* **`PreInvocation`:** Injects your enabled `checklists/*.md` (`code-quality`, `pr-quality`) as a transient `ephemeralMessage` at turn start (zero permanent context bloat).
* **`Stop` (pre-turn-end gate):** Before the agent finishes its turn (`NO_TOOL_CALL`), runs `lints lint` on any dirty `.py` / `.ts` files in the workspace. If errors exist, blocks stop (`{"decision": "continue"}`) and feeds the exact lint errors back so the agent self-fixes before handing back control.

---

## PR-Based Rule Sync Workflow

```sh
lints sync                        # Checkout/pull latest merged main & rebuild configs
lints propose "add no-date-now"   # Run `lints test` -> push branch -> open/update GitHub PR
lints merge                       # Squash-merge PR, delete branch, and sync local main
```

---

## CLI Reference

```sh
lints lint [paths...]             # Lint configured `target` directory (or explicit paths)
lints fix [paths...]              # Auto-fix & format Python (`ruff`) and TS (`oxlint`)
lints checklist                   # Print enabled model self-check lists (`checklists/*.md`)
lints list                        # List all rules (`[on]`/`[off]`, `ast`/`cfg`, summary)
lints enable ts/no-process-env    # Enable rule in config.toml (--local for ./lints.toml)
lints disable ts/no-default-export # Disable rule in config.toml (--local for ./lints.toml)
lints target ~/code/my-app        # Set default folder linted by `lints lint` (--local for project)
lints new ts/no-date-now          # Scaffold a new self-contained rule folder + tests
lints test [rule]                 # Run hermetic valid/invalid fixture tests per rule
lints explain ts/no-type-assertion # Print README + invalid/valid test fixtures for agents
lints hook install                # Install Antigravity PreInvocation + Stop hooks (--local optional)
```
