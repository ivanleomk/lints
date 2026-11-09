# `ts/no-multiline-ternary`

## Why
Multi-line and nested `? ... : ...` ternaries compress branching logic into dense expressions where fallback branches hide easily.

## How to Fix
Rewrite multi-line ternaries in `.ts` modules as explicit `if / else` blocks or `switch / case` statements (`.tsx` JSX trees remain exempt for single-level conditional rendering).
