def parse_int(raw: str) -> int | None:
    try:
        return int(raw)
    except Exception:
        return None
