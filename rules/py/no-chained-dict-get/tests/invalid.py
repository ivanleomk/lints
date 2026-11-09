def extract_email(payload: dict[str, object]) -> object:
    return payload.get("author", {}).get("email")  # type: ignore[attr-defined]
