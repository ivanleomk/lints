import os


def run_seed_script() -> str:
    return os.environ["DATABASE_URL"]
