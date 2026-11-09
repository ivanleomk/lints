# `py/no-multiline-ternary` (`PY003`)

## Why
Multi-line conditional expressions (`a if cond else b`) invert normal control-flow reading order. This rule also ignores Ruff's `SIM108` so Ruff never asks you to collapse explicit `if / else` blocks into ternaries.

## How to Fix
Write an explicit `if / else` block.
