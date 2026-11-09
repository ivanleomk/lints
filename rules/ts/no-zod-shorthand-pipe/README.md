# `ts/no-zod-shorthand-pipe`

## Why
Chaining `.transform(...).pipe(...)` to coerce shorthand strings into objects obscures wire contracts and breaks clean JSON Schema generation.

## How to Fix
Define explicit fields on a canonical `z.object({ ... })` schema.
