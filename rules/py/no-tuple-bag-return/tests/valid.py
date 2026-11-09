from dataclasses import dataclass


@dataclass
class AuthResult:
    token: str
    ttl_seconds: int
    scopes: list[str]


def authenticate(token: str) -> AuthResult:
    return AuthResult(token=token, ttl_seconds=3600, scopes=["read"])
