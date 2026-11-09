import pytest


@pytest.mark.parametrize(("x", "y"), [(1, 2)])
def test_increment(x: int, y: int) -> None:
    assert x + 1 == y
