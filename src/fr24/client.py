from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from fr24sdk.client import Client
from fr24sdk.exceptions import RateLimitError


@dataclass(frozen=True)
class Fr24Credits:
    consumed: int | None
    remaining: int | None


@dataclass(frozen=True)
class Fr24Response:
    flights: list[dict]
    credits: Fr24Credits | None
    error: str | None
    rate_limited: bool = False


def _coerce_dict(item: Any) -> dict:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    return {}


def _normalize_positions(result: Any) -> list[dict]:
    if result is None:
        return []
    items = None
    if isinstance(result, dict):
        if isinstance(result.get("data"), list):
            items = result["data"]
        elif isinstance(result.get("items"), list):
            items = result["items"]
        elif isinstance(result.get("results"), list):
            items = result["results"]
    if items is None and hasattr(result, "data"):
        items = getattr(result, "data")
    if items is None and isinstance(result, list):
        items = result
    if items is None:
        try:
            items = list(result)
        except TypeError:
            return []
    return [_coerce_dict(item) for item in items if item is not None]


def _coerce_params(params: dict) -> dict:
    coerced: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, list):
            coerced[key] = ",".join(str(item) for item in value)
        else:
            coerced[key] = str(value)
    return coerced


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _extract_credits(headers) -> Fr24Credits | None:
    consumed = _parse_int(headers.get("x-fr24-credits-consumed"))
    remaining = _parse_int(headers.get("x-fr24-credits-remaining"))
    if consumed is None and remaining is None:
        return None
    return Fr24Credits(consumed=consumed, remaining=remaining)


class Fr24Client:
    def __init__(self, api_token: str, max_requests_per_min: int) -> None:
        self._api_token = api_token
        self._log = logging.getLogger(__name__)
        self._rate_limiter = _RateLimiter(max_requests_per_min)

    async def fetch_by_aircraft(self, code: str) -> Fr24Response:
        return await self._call({"aircraft": code})

    async def fetch_by_airport_inbound(self, code: str) -> Fr24Response:
        return await self._call({"airports": f"inbound:{code}"})

    async def _call(self, params: dict) -> Fr24Response:
        await self._rate_limiter.wait()

        def _sync_call() -> tuple[dict, Fr24Credits | None]:
            with Client(api_token=self._api_token) as client:
                response = client.transport.request(
                    "GET",
                    "/api/live/flight-positions/full",
                    params=_coerce_params(params),
                )
                credits = _extract_credits(response.headers)
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                return payload, credits

        try:
            self._log.debug("FR24 request params=%s", params)
            payload, credits = await asyncio.to_thread(_sync_call)
        except RateLimitError as exc:
            await self._rate_limiter.cooldown(60)
            self._log.warning("FR24 rate limit hit; backing off for 60 seconds")
            error = f"{type(exc).__name__}: {exc}"
            return Fr24Response(flights=[], credits=None, error=error, rate_limited=True)
        except Exception as exc:
            self._log.exception("FR24 request failed params=%s", params)
            error = f"{type(exc).__name__}: {exc}"
            return Fr24Response(flights=[], credits=None, error=error, rate_limited=False)
        flights = _normalize_positions(payload)
        return Fr24Response(flights=flights, credits=credits, error=None, rate_limited=False)


class _RateLimiter:
    def __init__(self, max_requests_per_min: int) -> None:
        self._min_interval = 60.0 / max(1, max_requests_per_min)
        self._lock = asyncio.Lock()
        self._next_at = 0.0
        self._cooldown_until = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if now < self._cooldown_until:
                await asyncio.sleep(self._cooldown_until - now)
                now = time.monotonic()
            if now < self._next_at:
                await asyncio.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = now + self._min_interval

    async def cooldown(self, seconds: float) -> None:
        if seconds <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            until = now + seconds
            if until > self._cooldown_until:
                self._cooldown_until = until
            if until > self._next_at:
                self._next_at = until + self._min_interval
