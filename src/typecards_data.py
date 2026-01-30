from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable

_VALID_RE = re.compile(r"^[A-Z0-9]{2,4}$")
_DEFAULT_PATH = "all_icaos.json"


def _normalize_codes(values: Iterable[dict]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        raw = value.get("icao")
        if not raw:
            continue
        cleaned = str(raw).strip().upper()
        if not cleaned:
            continue
        if not _VALID_RE.match(cleaned):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _extract_codes(payload) -> list[dict] | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("aircraft")
    if isinstance(value, list):
        return value
    return None


def load_all_icaos(path: str | None = None) -> list[str]:
    log = logging.getLogger(__name__)
    source_path = path or _DEFAULT_PATH
    candidate: list[dict] | None = None
    try:
        payload = json.loads(Path(source_path).read_text(encoding="utf-8"))
        extracted = _extract_codes(payload)
        if extracted is None:
            log.warning("Typecards ICAO list missing aircraft array: %s", source_path)
        else:
            candidate = extracted
    except FileNotFoundError:
        log.warning("Typecards ICAO list not found: %s", source_path)
    except Exception as exc:
        log.warning("Failed to read typecards ICAO list %s: %s", source_path, exc)

    if candidate is None:
        return []
    normalized = _normalize_codes(candidate)
    if not normalized:
        log.warning("Typecards ICAO list is empty after normalization")
    return normalized
