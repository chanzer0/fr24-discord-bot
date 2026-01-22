from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from fr24sdk.client import Client
from fr24sdk.exceptions import RateLimitError, TransportError


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


def _normalize_params(params: dict, coerce_lists: bool) -> dict:
    normalized: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, list):
            cleaned = [item for item in value if item is not None and item != ""]
            if not cleaned:
                continue
            normalized[key] = (
                ",".join(str(item) for item in cleaned) if coerce_lists else cleaned
            )
        else:
            normalized[key] = str(value)
    return normalized


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
        self._client: Client | None = None

    async def fetch_by_aircraft(self, code: str) -> Fr24Response:
        return await self._call({"aircraft": code})

    @staticmethod
    def is_param_error(error: str | None) -> bool:
        if not error:
            return False
        lowered = error.lower()
        tokens = (
            "badrequest",
            "bad request",
            "validation",
            "pydantic",
            "invalid format",
            "list_type",
            "pattern",
        )
        return any(token in lowered for token in tokens)

    async def fetch_by_aircraft_batch(self, codes: list[str]) -> Fr24Response:
        cleaned = [str(code).strip().upper() for code in codes if str(code).strip()]
        if not cleaned:
            return Fr24Response(flights=[], credits=None, error=None, rate_limited=False)
        if len(cleaned) == 1:
            return await self.fetch_by_aircraft(cleaned[0])

        attempts = [
            ("comma", {"aircraft": ",".join(cleaned)}, False),
            ("list", {"aircraft": cleaned}, False),
            ("raw", {"aircraft": cleaned}, True),
        ]
        errors: list[str] = []
        for label, params, coerce in attempts:
            result = await self._call_transport(params, coerce_lists=coerce)
            if result.rate_limited:
                self._log.warning(
                    "FR24 aircraft batch rate limited strategy=%s size=%s",
                    label,
                    len(cleaned),
                )
                return result
            if result.error:
                self._log.warning(
                    "FR24 aircraft batch failed strategy=%s size=%s error=%s",
                    label,
                    len(cleaned),
                    result.error,
                )
                errors.append(f"{label}: {result.error}")
                if not self.is_param_error(result.error):
                    return result
                continue
            self._log.info(
                "FR24 aircraft batch succeeded strategy=%s size=%s",
                label,
                len(cleaned),
            )
            return result

        return Fr24Response(
            flights=[],
            credits=None,
            error="; ".join(errors) if errors else "Batch request failed",
            rate_limited=False,
        )

    async def fetch_by_airport_inbound(self, code: str) -> Fr24Response:
        return await self._call({"airports": f"inbound:{code}"})

    async def fetch_by_airports_inbound(self, codes: list[str]) -> Fr24Response:
        if not codes:
            return Fr24Response(flights=[], credits=None, error=None, rate_limited=False)
        parts = [f"inbound:{code}" for code in codes]
        attempts = [
            ("comma", {"airports": ",".join(parts)}, False),
            ("list", {"airports": parts}, False),
            ("raw", {"airports": parts}, True),
        ]
        errors: list[str] = []
        for label, params, coerce in attempts:
            result = await self._call_transport(params, coerce_lists=coerce)
            if result.rate_limited:
                self._log.warning(
                    "FR24 airport batch rate limited strategy=%s size=%s",
                    label,
                    len(parts),
                )
                return result
            if result.error:
                self._log.warning(
                    "FR24 airport batch failed strategy=%s size=%s error=%s",
                    label,
                    len(parts),
                    result.error,
                )
                errors.append(f"{label}: {result.error}")
                if not self.is_param_error(result.error):
                    return result
                continue
            self._log.info(
                "FR24 airport batch succeeded strategy=%s size=%s",
                label,
                len(parts),
            )
            return result

        return Fr24Response(
            flights=[],
            credits=None,
            error="; ".join(errors) if errors else "Batch request failed",
            rate_limited=False,
        )

    async def _call(self, params: dict) -> Fr24Response:
        return await self._call_transport(params, coerce_lists=True)

    async def _call_transport(self, params: dict, coerce_lists: bool) -> Fr24Response:
        await self._rate_limiter.wait()
        client = await self._ensure_client()

        def _sync_call() -> tuple[dict, Fr24Credits | None]:
            response = client.transport.request(
                "GET",
                "/api/live/flight-positions/full",
                params=_normalize_params(params, coerce_lists=coerce_lists),
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
        except TransportError as exc:
            snapshot = await self._rate_limiter.snapshot()
            self._log.exception(
                "FR24 transport error params=%s limiter=%s", params, snapshot
            )
            error = f"{type(exc).__name__}: {exc}"
            return Fr24Response(flights=[], credits=None, error=error, rate_limited=False)
        except Exception as exc:
            self._log.exception("FR24 request failed params=%s", params)
            error = f"{type(exc).__name__}: {exc}"
            return Fr24Response(flights=[], credits=None, error=error, rate_limited=False)
        flights = _normalize_positions(payload)
        return Fr24Response(flights=flights, credits=credits, error=None, rate_limited=False)

    async def _ensure_client(self) -> Client:
        if self._client is None:
            self._client = Client(api_token=self._api_token)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await asyncio.to_thread(self._client.transport.close)
            self._client = None


class _RateLimiter:
    def __init__(
        self,
        max_requests_per_min: int,
        base_spacing_padding_seconds: float = 0.5,
    ) -> None:
        self._max_requests = max(1, max_requests_per_min)
        self._window_seconds = 60.0
        base_spacing_seconds = self._window_seconds / self._max_requests
        self._min_interval = base_spacing_seconds + base_spacing_padding_seconds
        self._lock = asyncio.Lock()
        self._next_at = 0.0
        self._cooldown_until = 0.0
        self._recent = deque()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if now < self._cooldown_until:
                await asyncio.sleep(self._cooldown_until - now)
                now = time.monotonic()
            self._prune(now)
            if len(self._recent) >= self._max_requests:
                wait_for = (self._recent[0] + self._window_seconds) - now
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                    now = time.monotonic()
                    self._prune(now)
            if now < self._next_at:
                await asyncio.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = now + self._min_interval
            self._recent.append(now)

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

    async def snapshot(self) -> dict[str, float | int]:
        async with self._lock:
            now = time.monotonic()
            self._prune(now)
            return {
                "recent": len(self._recent),
                "min_interval": self._min_interval,
                "next_in": max(0.0, self._next_at - now),
                "cooldown_in": max(0.0, self._cooldown_until - now),
            }

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._recent and self._recent[0] <= cutoff:
            self._recent.popleft()
