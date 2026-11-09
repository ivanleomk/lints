def authenticate(token: str) -> tuple[str, int, list[str]]:
    return token, 3600, ["read"]
