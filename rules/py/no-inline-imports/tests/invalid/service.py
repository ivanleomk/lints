def serialize(payload: dict[str, int]) -> str:
    import json

    return json.dumps(payload)
