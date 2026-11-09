# `ts/no-inline-test-fixture`

## Why
Large multi-line YAML/JSON template strings inline inside `*.test.ts` bloat test files and discourage parameterized coverage.

## How to Fix
Place fixture payloads in `tests/assets/` and iterate test cases with `it.each(...)`.
