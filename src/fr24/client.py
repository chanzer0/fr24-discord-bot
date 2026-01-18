from __future__ import annotations

import asyncio
import logging
from typing import Any

from fr24sdk.client import Client


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


class Fr24Client:
    def __init__(self, api_token: str) -> None:
        self._api_token = api_token
        self._log = logging.getLogger(__name__)

    async def fetch_by_aircraft(self, code: str) -> list[dict]:
        return await self._call({"operating_as": code})

    async def fetch_by_airport_inbound(self, code: str) -> list[dict]:
        return await self._call({"airports": f"inbound:{code}"})

    async def _call(self, params: dict) -> list[dict]:
        def _sync_call() -> Any:
            with Client(api_token=self._api_token) as client:
                return client.live.flight_positions.get_full(**params)

        try:
            result = await asyncio.to_thread(_sync_call)
        except Exception:
            self._log.exception("FR24 request failed", extra={"params": params})
            return []
        return _normalize_positions(result)
