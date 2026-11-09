def parse_int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None
