# `lints`

Centralised, self-contained **Ruff** + **Oxlint** lint rules controlled via [`config.toml`](./config.toml), powered by `uv` + `.ts` plugins, and synced across machines every 60 seconds.

## Setup on Any Machine

```sh
git clone https://github.com/ivanleomk/lints.git ~/.config/lints
~/.config/lints/bin/lints bootstrap
```

`lints bootstrap` installs the `lints` CLI via `uv tool install --editable`, installs global `ruff` (via `uv`) and `oxlint`, symlinks `~/.config/ruff/ruff.toml` and `~/oxlint.config.ts`, and starts the 60-second background auto-pull daemon.

*(Use `git@github.com:ivanleomk/lints.git` or `gh auth setup-git` on machines where you also run `lints push`.)*

---

## Configuring via `config.toml`

[`config.toml`](./config.toml) controls your default target folder, rules folder, and enabled rules:

```toml
[lints]
target = "."        # Folder linted when you run `lints lint` with no path arguments
rules_dir = "rules" # Folder containing `ts/<rule>` and `py/<rule>` directories

[ts]
no-nullish-coalescing = true
no-type-assertion = true
no-default-export = true
# ...

[py]
no-getattr = true
no-silent-model-default = true
# ...
```

You can also place a `lints.toml` inside any individual project to set that project's default `target` (e.g. `target = "src"`) or disable/enable specific rules locally (`lints disable ts/no-default-export --local`).

---

## Self-Contained Rule Layout (`rules/<ts|py>/<rule-name>/`)

Every rule is a standalone directory so humans and AI coding agents can read, test, or author a rule in isolation:

```text
rules/
├── ts/<rule-name>/
│   ├── rule.json         # Summary + optional built-in Oxlint rules/overrides
│   ├── README.md         # Why it exists + how an agent should fix violations
│   ├── rule.ts           # Optional custom TypeScript AST rule (`export const rule`)
│   └── tests/
│       ├── invalid.ts    # Verified to FAIL this rule in isolation
│       └── valid.ts      # Verified to PASS this rule in isolation
└── py/<rule-name>/
    ├── rule.json         # Summary + Ruff rule codes or custom `PY00X` code
    ├── README.md
    ├── rule.py           # Optional custom Python `ast` rule (`def check(...)`)
    └── tests/
        ├── invalid.py
        └── valid.py
```

---

## CLI Reference

```sh
lints lint [paths...]             # Lint configured `target` directory (or explicit paths)
lints fix [paths...]              # Auto-fix & format Python (`ruff`) and TS (`oxlint`)
lints list                        # List all rules (`[on]`/`[off]`, `ast`/`cfg`, summary)
lints enable ts/no-process-env    # Enable rule in config.toml (--local for ./lints.toml)
lints disable ts/no-default-export # Disable rule in config.toml (--local for ./lints.toml)
lints target ~/code/my-app        # Set default folder linted by `lints lint` (--local for project)
lints rules-dir ./rules           # Set main rules folder directory in config.toml
lints new ts/no-date-now          # Scaffold a new self-contained rule folder + tests
lints test [rule]                 # Run hermetic valid/invalid fixture tests per rule
lints explain ts/no-type-assertion # Print README + invalid/valid test fixtures for agents
lints push [message]              # Run `lints test` -> compile configs -> commit & push
lints update                      # Pull latest rules immediately (--tools upgrades binaries)
lints status                      # Show git, symlinks, linter binaries, and 60s sync status
```
