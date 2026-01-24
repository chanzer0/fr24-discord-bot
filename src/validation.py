def normalize_code(sub_type: str, code: str) -> str | None:
    value = code.strip().upper()
    if len(value) < 2:
        return None
    if sub_type in ("aircraft", "airport"):
        return value
    if sub_type == "registration":
        cleaned = value.replace(" ", "")
        if len(cleaned) < 2:
            return None
        if not all(ch.isalnum() or ch == "-" for ch in cleaned):
            return None
        return cleaned
    return None
