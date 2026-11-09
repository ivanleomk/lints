# `ts/no-default-config-singleton`

## Why
Exported `DEFAULT_*_CONFIG = { ... }` objects act as silent fallback configurations when callers forget to supply real settings.

## How to Fix
Validate configuration through a schema at startup and throw a clear error if required configuration is missing.
