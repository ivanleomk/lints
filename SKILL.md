---
name: lints
description: >-
  Core engineering mindset and `lints` workflow: build in small vertical slices,
  verify end-to-end without mocks, enforce strict Ruff/Oxlint/AST rules, ask the
  user when requirements or rule trade-offs are ambiguous, and propose new
  self-contained lint rules. Activate whenever writing, reviewing, or linting
  Python or TypeScript code.
---

# Engineering Mindset & `lints` Workflow

Default posture: **move deliberately in small vertical slices, prove every slice works for real, keep `lints` green, and ask rather than guess.**

## 1. How to Think About Code (Vertical Slices & Real Verification)

- **Small, complete vertical slices:** Ship one narrow end-to-end path at a time (schema → logic → real caller → verification) instead of wide, unverified scaffolding. For multi-part changes, align on a ~30–40 line API + file skeleton with the user first.
- **No mocks, stubs, or silent fallbacks:** Exercise real schemas (Zod / Pydantic), real SQLite/files/CLI/HTTP routes, and real data fixtures (`tests/assets/` + `it.each` / `@pytest.mark.parametrize`). Never write tests that merely assert a mock returned its own canned value, and never mask missing config/data with silent fallbacks or no-op stubs.
- **Decide how to verify *before* coding:** Every slice needs executable proof—run the real CLI, server/client script, or integration test across live boundaries and inspect actual stdout/state before calling a slice done.
- **Ask early when unsure:** If product behavior, data contracts, or boundaries are ambiguous, stop and ask the user concisely instead of inventing speculative shims or backwards-compatibility layers.

## 2. Linting Loop (Write Good Code, Don't Game the Linter)

Ensure `lints` is available (`command -v lints`, or clone `https://github.com/ivanleomk/lints.git` to `~/.config/lints` and run `~/.config/lints/bin/lints bootstrap`), then run it on every slice:

```sh
lints lint [paths...]          # Run Ruff + custom Python AST + Oxlint
lints fix [paths...]           # Auto-fix & format Python and TypeScript
lints checklist                # Review active code-quality & pr-quality checklists
lints explain <rule-id>        # Read a rule's rationale + invalid/valid fixtures
```

- **Fix the root smell, never suppress blindly:** Do not add `# noqa`, `oxlint-disable`, `@ts-ignore`, or unsafe casts just to turn the linter green. Read `lints explain <rule-id>` and refactor to the canonical pattern.
- **Escalate genuine conflicts to the user:** If a rule genuinely conflicts with a project or framework constraint, explain the trade-off and ask the user before running `lints disable <id> --local` (which writes `./lints.toml`).

## 3. How Lints Are Evaluated & How to Propose New Lints

### How Evaluation Works
1. **Source of truth:** `~/.config/lints/config.toml` sets the default `target` folder and `[ts]` / `[py]` booleans (merged with any project-local `./lints.toml`).
2. **Self-contained rules:** Each rule lives in `rules/<ts|py>/<name>/` with `rule.json`, `README.md`, optional `rule.ts` or `rule.py` AST check, and `tests/{invalid,valid}*`.
3. **Compilation & isolated testing:** `lints build` compiles enabled rules into `ruff.toml` and `.generated/oxlint-plugin.ts` (loaded by `oxlint.config.ts`). `lints test [rule]` spins up a hermetic temp config per rule and verifies every `invalid*` fixture fails and every `valid*` fixture passes in isolation.

### Proposing a New Lint
When a bug pattern or review correction recurs, encode it as a rule instead of prose:

```sh
lints sync                                          # Pull latest merged `main`
lints new ts/no-date-now --summary "One-line why"   # Scaffold rule folder + fixtures
# Edit rule.ts / rule.py (include Fix + `lints explain` in message) and tests/{invalid,valid}*
lints test ts/no-date-now                           # Verify rule hermetically
lints propose "feat: add ts/no-date-now"            # Test all rules -> push branch -> open PR
lints merge                                         # Squash-merge PR & sync `main` (once approved)
```

Optional pre-turn-end & checklist hook (`--local` scopes to current repo):
```sh
lints hook install --agent <antigravity|claude|codex|git> [--local]
```
