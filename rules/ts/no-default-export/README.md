# `ts/no-default-export`

## Why
Default exports let every importer invent a different local name (`import foo from "./user"`), breaking exact `ripgrep` symbol searches for humans and AI agents.

## How to Fix
Use named exports (`export function createUser()`, `export const USER_LIMIT = 10`). Framework entrypoints (`*.config.*`, Next.js `page.tsx`/`layout.tsx`, `.stories.*`) are automatically exempted.
