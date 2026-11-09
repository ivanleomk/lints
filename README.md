# `lints`

Centralised **Ruff** + **Oxlint** configuration, custom AST plugins, and 1-minute background sync across macOS & Linux machines.

## Setup on Any Computer

```sh
git clone git@github.com:ivanleomk/lints.git ~/.config/lints
~/.config/lints/bin/lints bootstrap
```

`lints bootstrap` sets up:
1. `~/.config/ruff/ruff.toml` → `ruff.toml` (auto-discovered by Ruff CLI & IDE extensions)
2. `~/oxlint.config.mts` → `oxlint.config.mts` (auto-discovered by Oxlint CLI & IDE extensions across `~`)
3. `~/.local/bin/lints` → `bin/lints`
4. Global `ruff` & `oxlint` binaries (via `uv` and `bun`/`npm`)
5. A lightweight 60-second background auto-pull timer (`launchd` on macOS, `systemd --user` or `crontab` on Linux)

Pass `--with-git-hook` to `lints bootstrap` if you also want Git to lint staged `.py` and `.ts/.js` files globally before every commit.

## CLI Reference

```sh
lints                  # Lint Python + JS/TS files in current directory
lints check [paths...] # Same as `lints`, targeting specific files/folders
lints fix [paths...]   # Run ruff --fix + ruff format + oxlint --fix
lints edit ruff        # Edit central ruff.toml in $EDITOR
lints edit ts          # Edit central oxlint.base.json in $EDITOR
lints edit plugins     # Edit custom Oxlint AST rules in plugins/custom.mjs
lints validate         # Validate central Ruff & Oxlint configs + JS plugins
lints push [msg]       # Validate -> commit -> pull --rebase -> push to GitHub
lints update           # Pull latest rules immediately (--tools upgrades binaries)
lints scan ~/code      # Find old scattered per-project ruff/oxlint configs
lints status           # Show git state, symlinks, linter paths, and 60s sync status
lints daemon status    # Inspect/manage background timer (install|uninstall|status|tick)
```

## Per-Project Overrides (When Needed)

### Python (`ruff.toml`)
```toml
extend = "~/.config/ruff/ruff.toml"

[lint]
ignore = ["B008"]
```

### TypeScript / JavaScript (`oxlint.config.mts`)
```ts
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const { default: base } = await import(
  pathToFileURL(path.join(os.homedir(), "oxlint.config.mts")).href
);

export default {
  ...base,
  rules: {
    ...base.rules,
    "no-console": "off",
  },
};
```
