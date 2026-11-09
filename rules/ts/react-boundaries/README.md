# `ts/react-boundaries`

## Why
Calling React hooks conditionally corrupts hook state, and exporting arbitrary helper functions from `.tsx` files breaks Fast Refresh and blurs UI vs logic modules.

## How to Fix
Call `use*` hooks only at the top level of components/hooks, and move non-component helper functions out of `.tsx` files into `.ts` modules.
