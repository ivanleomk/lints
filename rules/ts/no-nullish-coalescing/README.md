# `ts/no-nullish-coalescing`

## Why
`??` and `??=` encourage silent fallback values that mask missing config, broken upstream payloads, or uninitialized state.

## How to Fix
1. Validate inputs at the boundary (e.g. Zod schema `.default(...)` or required field).
2. Use a function parameter default (`function connect(timeoutMs = 5000)`).
3. Branch explicitly and fail fast (`if (config.port === undefined) throw new Error(...)`).
