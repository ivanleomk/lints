def read_name(record: object) -> str | None:
    return getattr(record, "name", None)
