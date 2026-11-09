# `py/no-inline-imports`

## Why
Hiding `import` statements inside functions obscures module dependencies and defers missing-package or circular-import crashes until runtime.

## How to Fix
Move all imports to the top of the file. If two modules have a circular import, extract shared types into a dedicated `types.py` / `models.py` module.
