# `ts/no-process-env`

## Why
Reading `process.env.FOO` or `Bun.env.FOO` directly inside routes and services hides configuration requirements and skips startup validation.

## How to Fix
Parse `process.env` once inside `env.ts` (e.g. with Zod) and import the typed `env` object everywhere else.
