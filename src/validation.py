import re


_AIRCRAFT_RE = re.compile(r"^[A-Z0-9]{3,6}$")
_AIRPORT_RE = re.compile(r"^[A-Z]{4}$")


def normalize_code(sub_type: str, code: str) -> str | None:
    value = code.strip().upper()
    if sub_type == "aircraft":
        return value if _AIRCRAFT_RE.fullmatch(value) else None
    if sub_type == "airport":
        return value if _AIRPORT_RE.fullmatch(value) else None
    return None
