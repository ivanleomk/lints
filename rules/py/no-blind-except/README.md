# `py/no-blind-except`

## Why
Catching `Exception` (or bare `except:`) and returning `None` / `False` swallows bugs, validation failures, and unexpected runtime errors.

## How to Fix
Catch the specific exception class you expect (`ValueError`, `KeyError`, `httpx.HTTPError`), or re-raise after cleanup.
