# Authoring & Understanding Rules (`AGENTS.md`)

Inspired by [Factory's *Using Linters to Direct Agents*](https://factory.ai/news/using-linters-to-direct-agents), every lint in this repository is a **self-contained directory** under `rules/ts/<name>/` or `rules/py/<name>/`.

## How Agents Should Use This Repo

1. **When a lint error fires:** Run `lints explain <rule-id>` (e.g. `lints explain ts/no-nullish-coalescing` or `lints explain PY001`) to view the rule's `README.md` alongside its `invalid` and `valid` test fixtures.
2. **When toggling rules or setting a target folder:** Edit [`config.toml`](./config.toml) (or run `lints enable <id>`, `lints disable <id>`, `lints target <dir>`) and run `lints build`. For project-local overrides, use `--local` (writes `./lints.toml`).
3. **When creating a new lint:**
   * Run `uv run lints new ts/<name> --summary "..."` or `uv run lints new py/<name> --summary "..."`.
   * Implement the check in `rule.ts` (TypeScript) or `rule.py` / `rule.json` (Python). Ensure error messages state **what** is banned, **Fix:** how to rewrite it, and **Docs:** `lints explain <lang>/<name>`.
   * Add concrete failing and passing examples in `tests/invalid*` and `tests/valid*`.
   * Verify hermetically with `uv run lints test <lang>/<name>` before running `lints propose`.
