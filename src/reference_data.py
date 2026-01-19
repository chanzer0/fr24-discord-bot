from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Iterable
from urllib.request import Request, urlopen

from .utils import utc_now_iso


_DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class AirportRef:
    icao: str
    iata: str | None
    name: str
    city: str
    place_code: str
    search_key: str


@dataclass(frozen=True)
class ModelRef:
    icao: str
    manufacturer: str
    name: str
    search_key: str


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _normalize_code(value: str | None) -> str:
    return (value or "").strip().upper()


def _build_airport_ref(row: dict) -> AirportRef | None:
    icao = _normalize_code(row.get("icao"))
    if not icao:
        return None
    iata = _normalize_code(row.get("iata")) or None
    name = _normalize_text(row.get("name"))
    city = _normalize_text(row.get("city"))
    place_code = _normalize_code(row.get("place_code") or row.get("placeCode"))
    search_key = " ".join(
        part
        for part in (
            icao,
            iata or "",
            name,
            city,
            place_code,
        )
        if part
    ).lower()
    return AirportRef(
        icao=icao,
        iata=iata,
        name=name,
        city=city,
        place_code=place_code,
        search_key=search_key,
    )


def _build_model_ref(row: dict) -> ModelRef | None:
    icao = _normalize_code(row.get("icao") or row.get("id"))
    if not icao:
        return None
    manufacturer = _normalize_text(row.get("manufacturer"))
    name = _normalize_text(row.get("name"))
    search_key = " ".join(part for part in (icao, manufacturer, name) if part).lower()
    return ModelRef(
        icao=icao,
        manufacturer=manufacturer,
        name=name,
        search_key=search_key,
    )


def format_airport_label(ref: AirportRef) -> str:
    code = ref.iata or ref.icao
    details_parts = [part for part in (ref.name, ref.city, ref.place_code) if part]
    details = ", ".join(details_parts)
    label = f"{code} - {details}" if details else code
    return label[:100]


def format_model_label(ref: ModelRef) -> str:
    details = " ".join(part for part in (ref.manufacturer, ref.name) if part)
    label = f"{ref.icao} - {details}" if details else ref.icao
    return label[:100]


def fetch_reference_payload_sync(
    base_url: str,
    endpoint: str,
    client_version: str,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    request = Request(
        url,
        headers={
            "x-client-version": client_version,
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
    return json.loads(payload)


async def fetch_reference_payload(
    base_url: str,
    endpoint: str,
    client_version: str,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    return await asyncio.to_thread(
        fetch_reference_payload_sync,
        base_url,
        endpoint,
        client_version,
        timeout_seconds,
    )


def parse_airports_payload(payload: dict) -> tuple[str | None, list[dict]]:
    updated_at = payload.get("updatedAt")
    rows = []
    for row in payload.get("rows", []):
        ref = _build_airport_ref(row)
        if not ref:
            continue
        rows.append(
            {
                "icao": ref.icao,
                "iata": ref.iata,
                "name": ref.name,
                "city": ref.city,
                "place_code": ref.place_code,
            }
        )
    return str(updated_at) if updated_at is not None else None, rows


def parse_models_payload(payload: dict) -> tuple[str | None, list[dict]]:
    updated_at = payload.get("updatedAt")
    blacklist = {
        _normalize_code(value)
        for value in payload.get("blacklist", [])
        if value is not None
    }
    rows = []
    for row in payload.get("rows", []):
        ref = _build_model_ref(row)
        if not ref or ref.icao in blacklist:
            continue
        rows.append(
            {
                "icao": ref.icao,
                "manufacturer": ref.manufacturer,
                "name": ref.name,
            }
        )
    return str(updated_at) if updated_at is not None else None, rows


class ReferenceDataCache:
    def __init__(self) -> None:
        self._airports: list[AirportRef] = []
        self._models: list[ModelRef] = []
        self._airports_by_icao: dict[str, AirportRef] = {}
        self._airports_by_iata: dict[str, AirportRef] = {}
        self._models_by_icao: dict[str, ModelRef] = {}

    def set_airports(self, rows: Iterable[dict]) -> None:
        refs = []
        iata_map: dict[str, AirportRef] = {}
        for row in rows:
            ref = _build_airport_ref(row)
            if ref:
                refs.append(ref)
                if ref.iata and ref.iata not in iata_map:
                    iata_map[ref.iata] = ref
        refs.sort(key=lambda item: item.icao)
        self._airports = refs
        self._airports_by_icao = {ref.icao: ref for ref in refs}
        self._airports_by_iata = iata_map

    def set_models(self, rows: Iterable[dict]) -> None:
        refs = []
        for row in rows:
            ref = _build_model_ref(row)
            if ref:
                refs.append(ref)
        refs.sort(key=lambda item: item.icao)
        self._models = refs
        self._models_by_icao = {ref.icao: ref for ref in refs}

    def has_airports(self) -> bool:
        return bool(self._airports)

    def has_models(self) -> bool:
        return bool(self._models)

    def get_airport(self, icao: str) -> AirportRef | None:
        return self._airports_by_icao.get(_normalize_code(icao))

    def get_airport_by_iata(self, iata: str) -> AirportRef | None:
        return self._airports_by_iata.get(_normalize_code(iata))

    def get_model(self, icao: str) -> ModelRef | None:
        return self._models_by_icao.get(_normalize_code(icao))

    def search_airports(self, query: str, limit: int = 25) -> list[AirportRef]:
        value = _normalize_text(query).lower()
        if not value:
            return []
        matches = []
        for ref in self._airports:
            if value in ref.search_key:
                matches.append(ref)
                if len(matches) >= limit:
                    break
        return matches

    def search_models(self, query: str, limit: int = 25) -> list[ModelRef]:
        value = _normalize_text(query).lower()
        if not value:
            return []
        matches = []
        for ref in self._models:
            if value in ref.search_key:
                matches.append(ref)
                if len(matches) >= limit:
                    break
        return matches


class ReferenceDataService:
    def __init__(self, db, base_url: str, client_version: str) -> None:
        self._db = db
        self._base_url = base_url
        self._client_version = client_version
        self._cache = ReferenceDataCache()
        self._lock = asyncio.Lock()

    async def load_from_db(self) -> dict[str, int]:
        airports = await self._db.fetch_reference_airports()
        models = await self._db.fetch_reference_models()
        async with self._lock:
            self._cache.set_airports(airports)
            self._cache.set_models(models)
        return {"airports": len(airports), "models": len(models)}

    async def refresh(self, dataset: str) -> dict[str, dict]:
        log = logging.getLogger(__name__)
        results: dict[str, dict] = {}
        if dataset not in ("airports", "models", "all"):
            raise ValueError("dataset must be airports, models, or all")
        datasets = (dataset,) if dataset != "all" else ("airports", "models")
        for target in datasets:
            endpoint = "airports" if target == "airports" else "models"
            log.info("Refreshing reference data: %s", target)
            payload = await fetch_reference_payload(
                self._base_url, endpoint, self._client_version
            )
            fetched_at = utc_now_iso()
            if target == "airports":
                updated_at, rows = parse_airports_payload(payload)
                await self._db.replace_reference_airports(rows, updated_at, fetched_at)
                async with self._lock:
                    self._cache.set_airports(rows)
            else:
                updated_at, rows = parse_models_payload(payload)
                await self._db.replace_reference_models(rows, updated_at, fetched_at)
                async with self._lock:
                    self._cache.set_models(rows)
            results[target] = {
                "rows": len(rows),
                "updated_at": updated_at,
                "fetched_at": fetched_at,
            }
        return results

    async def search_airports(self, query: str, limit: int = 25) -> list[AirportRef]:
        async with self._lock:
            return self._cache.search_airports(query, limit)

    async def search_models(self, query: str, limit: int = 25) -> list[ModelRef]:
        async with self._lock:
            return self._cache.search_models(query, limit)

    async def get_airport(self, icao: str) -> AirportRef | None:
        async with self._lock:
            return self._cache.get_airport(icao)

    async def get_airport_by_iata(self, iata: str) -> AirportRef | None:
        async with self._lock:
            return self._cache.get_airport_by_iata(iata)

    async def get_model(self, icao: str) -> ModelRef | None:
        async with self._lock:
            return self._cache.get_model(icao)

    async def has_airports(self) -> bool:
        async with self._lock:
            return self._cache.has_airports()

    async def has_models(self) -> bool:
        async with self._lock:
            return self._cache.has_models()
