# `ts/no-type-assertion`

## Why
Type assertions (`value as User`, `<User>value`) silence TypeScript without checking runtime values.

## How to Fix
1. Parse untrusted JSON/inputs at the boundary with a Zod schema (`UserSchema.parse(raw)`).
2. Narrow unions using discriminated tags, `in` / `typeof` / `instanceof` checks, or type predicates (`x is User`).
3. Literal narrowing with `as const` remains allowed.
