# `ts/no-explicit-any`

## Why
`any` disables type checking cleanly across callers and callees, letting invalid property reads propagate silently.

## How to Fix
Use a specific interface/type, a generic type parameter `<T>`, or `unknown` narrowed via runtime validation.
