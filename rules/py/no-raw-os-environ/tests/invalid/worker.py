import os


def read_api_key() -> str | None:
    return os.getenv("API_KEY")
