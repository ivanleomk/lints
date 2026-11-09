# `ts/ban-ts-comment`

## Why
Unexplained `@ts-ignore` and `@ts-nocheck` comments permanently mute type errors when interfaces evolve.

## How to Fix
Fix the underlying type mismatch, or use `// @ts-expect-error -- <reason at least 10 chars>` when testing deliberately invalid inputs.
