# `py/no-silent-model-default` (`PY001`)

## Why
Setting `field: str = ""` on a Pydantic `BaseModel` or `@dataclass` silently accepts missing wire/config fields instead of failing validation fast.

## How to Fix
Require the field (`field: str`) or make optionality explicit (`field: str | None = None`).
