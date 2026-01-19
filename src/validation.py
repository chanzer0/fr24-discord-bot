def normalize_code(sub_type: str, code: str) -> str | None:
    value = code.strip().upper()
    if len(value) < 2:
        return None
    if sub_type in ("aircraft", "airport"):
        return value
    return None
