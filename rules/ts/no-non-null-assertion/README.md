# `ts/no-non-null-assertion`

## Why
Postfix `!` (`user.email!`) turns potential `undefined`/`null` values into uncaught `TypeError` crashes without a clear error message.

## How to Fix
Guard explicitly (`if (!user.email) throw new Error("User missing email")`) before using the value.
