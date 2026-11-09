import json


def serialize(payload: dict[str, int]) -> str:
    return json.dumps(payload)
