# `ts/pure-barrel-index`

## Why
Mixing inline function/type/constant declarations into a barrel `index.ts` that also re-exports sibling modules hides where symbols actually live.

## How to Fix
Move inline declarations into dedicated modules (`types.ts`, `service.ts`) and keep `index.ts` strictly re-export statements.
