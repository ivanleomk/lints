# `py/no-chained-dict-get` (`PY005`)

## Why
Chained `payload.get("a", {}).get("b")` calls probe untyped nested dictionaries mid-program and silently coerce missing nested structures into `None`.

## How to Fix
Validate untrusted dictionaries once at the boundary using `BaseModel.model_validate(payload)` and read typed attributes (`model.a.b`).
