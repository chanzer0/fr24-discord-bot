from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx

try:
    from fr24 import grpc as fr24_grpc  # type: ignore
except Exception as exc:  # pragma: no cover - import guard
    fr24_grpc = None  # type: ignore
    _FR24_GRPC_IMPORT_ERROR = exc
else:
    _FR24_GRPC_IMPORT_ERROR = None

try:
    from fr24.proto import parse_data  # type: ignore
    from fr24.proto import v1_pb2  # type: ignore
except Exception as exc:  # pragma: no cover - import guard
    parse_data = None  # type: ignore
    v1_pb2 = None  # type: ignore
    _FR24_PROTO_IMPORT_ERROR = exc
else:
    _FR24_PROTO_IMPORT_ERROR = None

try:
    from fr24.proto.headers import get_grpc_headers  # type: ignore
except Exception:
    get_grpc_headers = None  # type: ignore

try:
    from fr24.utils import DEFAULT_HEADERS  # type: ignore
except Exception:
    DEFAULT_HEADERS = None  # type: ignore


def grpc_available() -> bool:
    return fr24_grpc is not None and parse_data is not None and v1_pb2 is not None


def grpc_import_error() -> Exception | None:
    return _FR24_GRPC_IMPORT_ERROR or _FR24_PROTO_IMPORT_ERROR


def build_headers() -> httpx.Headers:
    if get_grpc_headers is not None:
        return httpx.Headers(get_grpc_headers(auth=None))
    return httpx.Headers(DEFAULT_HEADERS or {})


def _format_flight_id(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{int(value):x}"
    except (TypeError, ValueError):
        cleaned = str(value).strip()
        return cleaned or None


def normalize_flight(record: dict[str, Any]) -> dict[str, Any]:
    flight = dict(record)
    typecode = flight.get("typecode")
    if typecode:
        flight["typecode"] = str(typecode).strip().upper()
    flight_id = (
        flight.get("flight_id")
        or flight.get("flightid")
        or flight.get("id")
        or flight.get("fr24_id")
    )
    formatted_id = _format_flight_id(flight_id)
    if formatted_id:
        flight["flight_id"] = formatted_id
    return flight


def build_flight_key(flight: dict) -> str | None:
    for key in ("flight_id", "flightid", "id", "fr24_id", "uuid"):
        value = flight.get(key)
        if value:
            return str(value)
    parts = [
        flight.get("callsign"),
        flight.get("flight_number"),
        flight.get("origin"),
        flight.get("destination"),
        flight.get("timestamp"),
    ]
    parts = [str(item) for item in parts if item]
    if parts:
        return "|".join(parts)
    try:
        payload = json.dumps(flight, sort_keys=True, default=str)
    except TypeError:
        payload = repr(flight)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


async def _call_live_feed(
    client: httpx.AsyncClient,
    icaos: list[str],
    feed_limit: int,
    headers: httpx.Headers,
) -> httpx.Response:
    if fr24_grpc is None:
        raise RuntimeError("fr24 gRPC module is unavailable")
    request = fr24_grpc.LiveFeedParams(
        bounding_box=fr24_grpc.BoundingBox(
            south=-90.0, north=90.0, west=-180.0, east=180.0
        ),
        limit=feed_limit,
        fields={"flight", "reg", "route", "type"},
    ).to_proto()
    request.filters_list.types_list.extend(icaos)
    return await fr24_grpc.live_feed(client, request, headers=headers)


async def fetch_batch(
    client: httpx.AsyncClient,
    icaos: list[str],
    feed_limit: int,
    headers: httpx.Headers,
) -> dict[str, dict[str, Any]]:
    if not grpc_available():
        raise RuntimeError("fr24 gRPC modules are unavailable")
    payloads: dict[str, dict[str, Any]] = {
        icao: {
            "icao": icao,
            "ok": False,
            "status_code": None,
            "matched_count": 0,
            "flights": [],
            "error": None,
        }
        for icao in icaos
    }

    try:
        response = await _call_live_feed(
            client=client,
            icaos=icaos,
            feed_limit=feed_limit,
            headers=headers,
        )
        status_code = response.status_code
        response.raise_for_status()
        parsed = parse_data(response.content, v1_pb2.LiveFeedResponse)
        if parsed.is_err():
            err = str(parsed.err())
            for payload in payloads.values():
                payload["status_code"] = status_code
                payload["error"] = err
            return payloads

        data = parsed.ok()
        grouped: dict[str, list[dict[str, Any]]] = {icao: [] for icao in icaos}
        for flight in data.flights_list:
            record = fr24_grpc.live_feed_flightdata_dict(flight)
            typecode = record.get("typecode")
            if not typecode:
                continue
            key = str(typecode).strip().upper()
            if key not in grouped:
                continue
            grouped[key].append(normalize_flight(record))

        for icao in icaos:
            flights = grouped.get(icao, [])
            payload = payloads[icao]
            payload["status_code"] = status_code
            payload["matched_count"] = len(flights)
            payload["flights"] = flights
            payload["ok"] = True
    except Exception as exc:
        err = str(exc)
        for payload in payloads.values():
            payload["error"] = err

    return payloads
