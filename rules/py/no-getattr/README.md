# `py/no-getattr`

## Why
`getattr(obj, "field", None)` hides missing attributes and bypasses type checkers.

## How to Fix
Validate untrusted objects into a `pydantic.BaseModel` or type the interface with a `typing.Protocol` and read `obj.field` directly.
