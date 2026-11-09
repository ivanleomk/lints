# `py/no-tuple-bag-return` (`PY002`)

## Why
Returning 3+ positional values as a tuple forces callers into brittle `_, _, token = fn()` unpacking.

## How to Fix
Return a named `@dataclass` or `pydantic.BaseModel` with explicit field names.
