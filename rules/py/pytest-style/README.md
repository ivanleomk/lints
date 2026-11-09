# `py/pytest-style`

## Why
Consistent `@pytest.mark.parametrize` signatures and specific `pytest.raises(..., match=...)` checks prevent vague, copy-pasted tests.

## How to Fix
Use tuple argument names in `@pytest.mark.parametrize(("input_val", "expected"), [...])` and avoid bare `pytest.raises(Exception)`.
