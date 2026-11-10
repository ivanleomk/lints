import os


def read_test_token() -> str | None:
    return os.getenv("TEST_TOKEN")
