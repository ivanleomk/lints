from dataclasses import dataclass


@dataclass
class Author:
    email: str


@dataclass
class EventPayload:
    author: Author


def extract_email(payload: EventPayload) -> str:
    return payload.author.email
