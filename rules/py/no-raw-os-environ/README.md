# `py/no-raw-os-environ` (`PY004`)

## Why
Reading `os.environ` or `os.getenv()` inside business logic scatters configuration dependencies and bypasses startup validation.

## How to Fix
Read and validate environment variables once inside `env.py`, `config.py`, or `settings.py` (e.g. via `pydantic-settings`) and pass typed settings into services.
