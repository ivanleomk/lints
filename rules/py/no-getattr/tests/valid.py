from typing import Protocol


class Named(Protocol):
    name: str


def read_name(record: Named) -> str:
    return record.name
