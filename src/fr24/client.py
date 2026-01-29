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
    no_active_keys: bool = False
    retry_after_seconds: int | None = None
    key_index: int | None = None
    key_suffix: str | None = None


class NoActiveKeysError(RuntimeError):
    def __init__(self, retry_after_seconds: float | None) -> None:
        super().__init__("No FR24 API keys available (all parked)")
        self.retry_after_seconds = retry_after_seconds


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
            cleaned = [item for item in value if item is not None and item != ""]
            if not cleaned:
                continue
            coerced[key] = ",".join(str(item) for item in cleaned)
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


@dataclass
class _KeyState:
    index: int
    token: str
    suffix: str
    client: Client
    limiter: "_RateLimiter"
    requests: int = 0
    last_used: float = 0.0
    parked_until: float | None = None
    parked_reason: str | None = None


class _SpacingLimiter:
    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(0.0, min_interval)
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    @property
    def min_interval(self) -> float:
        return self._min_interval

    async def wait(self) -> float:
        waited = 0.0
        async with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                waited = self._next_at - now
                await asyncio.sleep(waited)
                now = time.monotonic()
            self._next_at = now + self._min_interval
        return waited

    async def snapshot(self) -> dict[str, float]:
        async with self._lock:
            now = time.monotonic()
            return {
                "min_interval": self._min_interval,
                "next_in": max(0.0, self._next_at - now),
            }


class Fr24Client:
    def __init__(self, api_tokens: list[str], max_requests_per_min: int) -> None:
        if not api_tokens:
            raise ValueError("FR24 API keys list is empty")
        self._log = logging.getLogger(__name__)
        self._max_requests_per_min = max(1, max_requests_per_min)
        self._keys: list[_KeyState] = []
        for idx, token in enumerate(api_tokens):
            client = Client(api_token=token)
            limiter = _RateLimiter(self._max_requests_per_min)
            suffix = str(token).strip()[-4:] if str(token).strip() else "????"
            self._keys.append(
                _KeyState(
                    index=idx,
                    token=token,
                    suffix=suffix,
                    client=client,
                    limiter=limiter,
                )
            )
        self._select_lock = asyncio.Lock()
        self._rr_index = 0
        key_count = len(self._keys)
        per_key_min_interval = self._keys[0].limiter.min_interval
        pool_min_interval = (
            per_key_min_interval / key_count if key_count > 1 else 0.0
        )
        self._pool_limiter = _SpacingLimiter(pool_min_interval) if key_count > 1 else None
        self._log.info(
            "FR24 key pool initialized: keys=%s max_requests_per_min=%s",
            len(self._keys),
            self._max_requests_per_min,
        )
        for key in self._keys:
            self._log.info(
                "FR24 key[%s] limiter: min_interval=%.2fs",
                key.index,
                key.limiter.min_interval,
            )
        self._log.info(
            "FR24 pool pacing: key_count=%s per_key_min_interval=%.2fs pool_min_interval=%.2fs enabled=%s",
            key_count,
            per_key_min_interval,
            pool_min_interval,
            "yes" if self._pool_limiter else "no",
        )

    def _find_key_index_by_suffix(self, suffix: str) -> int | None:
        cleaned = str(suffix).strip()
        if not cleaned:
            return None
        for key in self._keys:
            if key.suffix == cleaned:
                return key.index
        return None

    def _active_key_count_locked(self, now: float) -> int:
        return sum(
            1
            for key in self._keys
            if not key.parked_until or key.parked_until <= now
        )

    def _next_unpark_in_locked(self, now: float) -> float | None:
        candidates = [
            key.parked_until
            for key in self._keys
            if key.parked_until and key.parked_until > now
        ]
        if not candidates:
            return None
        return max(0.0, min(candidates) - now)

    def _clear_expired_parks_locked(self, now: float) -> bool:
        changed = False
        for key in self._keys:
            if key.parked_until and key.parked_until <= now:
                key.parked_until = None
                key.parked_reason = None
                changed = True
        return changed

    def _refresh_pool_limiter_locked(self, active_count: int) -> None:
        per_key_min_interval = self._keys[0].limiter.min_interval
        if active_count <= 1:
            self._pool_limiter = None
            return
        pool_min_interval = per_key_min_interval / active_count
        self._pool_limiter = _SpacingLimiter(pool_min_interval)
        self._log.info(
            "FR24 pool pacing updated: active_keys=%s per_key_min_interval=%.2fs pool_min_interval=%.2fs",
            active_count,
            per_key_min_interval,
            pool_min_interval,
        )

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

    @staticmethod
    def is_credit_exhausted(error: str | None) -> bool:
        if not error:
            return False
        lowered = error.lower()
        tokens = (
            "credit",
            "credits",
            "insufficient",
            "exhausted",
            "no credits",
            "quota",
            "balance",
        )
        return any(token in lowered for token in tokens)

    async def fetch_by_aircraft_batch(self, codes: list[str]) -> Fr24Response:
        cleaned = [str(code).strip().upper() for code in codes if str(code).strip()]
        if not cleaned:
            return Fr24Response(flights=[], credits=None, error=None, rate_limited=False)
        if len(cleaned) == 1:
            return await self.fetch_by_aircraft(cleaned[0])
        return await self._call({"aircraft": ",".join(cleaned)})

    async def fetch_by_airport_inbound(self, code: str) -> Fr24Response:
        return await self._call({"airports": f"inbound:{code}"})

    async def fetch_by_airports_inbound(self, codes: list[str]) -> Fr24Response:
        if not codes:
            return Fr24Response(flights=[], credits=None, error=None, rate_limited=False)
        parts = [f"inbound:{code}" for code in codes]
        return await self._call({"airports": ",".join(parts)})

    async def fetch_by_registration(self, registration: str) -> Fr24Response:
        return await self._call_registration(registration)

    async def fetch_by_registration_batch(self, registrations: list[str]) -> Fr24Response:
        cleaned = [
            str(code).strip().upper().replace(" ", "")
            for code in registrations
            if str(code).strip()
        ]
        cleaned = [code for code in cleaned if code]
        if not cleaned:
            return Fr24Response(flights=[], credits=None, error=None, rate_limited=False)
        if len(cleaned) == 1:
            return await self.fetch_by_registration(cleaned[0])
        return await self._call_registration(",".join(cleaned))

    def reset_cycle_stats(self) -> None:
        for key in self._keys:
            key.requests = 0

    async def snapshot_keys(self) -> list[dict]:
        snapshots: list[dict] = []
        now = time.monotonic()
        wall_now = time.time()
        for key in self._keys:
            limiter = await key.limiter.snapshot()
            last_used_ago = None
            if key.last_used > 0:
                last_used_ago = max(0.0, now - key.last_used)
            parked_in = None
            if key.parked_until and key.parked_until > wall_now:
                parked_in = max(0.0, key.parked_until - wall_now)
            snapshots.append(
                {
                    "index": key.index,
                    "requests": key.requests,
                    "last_used_ago": last_used_ago,
                    "next_in": limiter["next_in"],
                    "cooldown_in": limiter["cooldown_in"],
                    "min_interval": limiter["min_interval"],
                    "recent": limiter["recent"],
                    "parked_until": key.parked_until,
                    "parked_reason": key.parked_reason,
                    "parked_in": parked_in,
                }
            )
        return snapshots

    async def active_key_count(self) -> int:
        async with self._select_lock:
            now = time.time()
            changed = self._clear_expired_parks_locked(now)
            count = sum(
                1
                for key in self._keys
                if not key.parked_until or key.parked_until <= now
            )
            if changed:
                self._refresh_pool_limiter_locked(count)
            return count

    async def next_unpark_in(self) -> float | None:
        async with self._select_lock:
            now = time.time()
            self._clear_expired_parks_locked(now)
            candidates = [
                key.parked_until
                for key in self._keys
                if key.parked_until and key.parked_until > now
            ]
            if not candidates:
                return None
            return max(0.0, min(candidates) - now)

    async def park_key_by_index(
        self, index: int, until_epoch: float, reason: str | None
    ) -> bool:
        async with self._select_lock:
            if index < 0 or index >= len(self._keys):
                return False
            now = time.time()
            self._clear_expired_parks_locked(now)
            before = self._active_key_count_locked(now)
            key = self._keys[index]
            key.parked_until = max(until_epoch, now)
            key.parked_reason = reason
            after = self._active_key_count_locked(now)
            if after != before:
                self._refresh_pool_limiter_locked(after)
            return True

    async def unpark_key_by_index(self, index: int) -> bool:
        async with self._select_lock:
            if index < 0 or index >= len(self._keys):
                return False
            now = time.time()
            self._clear_expired_parks_locked(now)
            before = self._active_key_count_locked(now)
            key = self._keys[index]
            key.parked_until = None
            key.parked_reason = None
            after = self._active_key_count_locked(now)
            if after != before:
                self._refresh_pool_limiter_locked(after)
            return True

    async def park_key_by_suffix(
        self, suffix: str, until_epoch: float, reason: str | None
    ) -> bool:
        index = self._find_key_index_by_suffix(suffix)
        if index is None:
            return False
        return await self.park_key_by_index(index, until_epoch, reason)

    async def unpark_key_by_suffix(self, suffix: str) -> bool:
        index = self._find_key_index_by_suffix(suffix)
        if index is None:
            return False
        return await self.unpark_key_by_index(index)

    async def _select_key(self) -> tuple[_KeyState, float]:
        async with self._select_lock:
            now = time.time()
            changed = self._clear_expired_parks_locked(now)
            statuses: list[tuple[_KeyState, dict | None, float, bool, float | None]] = []
            best_wait: float | None = None
            for key in self._keys:
                if key.parked_until and key.parked_until > now:
                    statuses.append(
                        (key, None, float("inf"), True, key.parked_until)
                    )
                    continue
                snapshot = await key.limiter.snapshot()
                wait_for = max(snapshot["next_in"], snapshot["cooldown_in"])
                statuses.append((key, snapshot, wait_for, False, None))
                if best_wait is None or wait_for < best_wait:
                    best_wait = wait_for
            if best_wait is None:
                if changed:
                    self._refresh_pool_limiter_locked(0)
                retry_after = self._next_unpark_in_locked(now)
                raise NoActiveKeysError(retry_after)
            selected_idx = None
            key_count = len(self._keys)
            for offset in range(key_count):
                idx = (self._rr_index + offset) % key_count
                if abs(statuses[idx][2] - best_wait) <= 0.001:
                    selected_idx = idx
                    break
            if selected_idx is None:
                selected_idx = 0
            self._rr_index = (selected_idx + 1) % key_count
            selected = statuses[selected_idx][0]
            status_text = self._format_key_statuses(statuses, now)
            self._log.debug(
                "FR24 key select: selected=%s/%s wait=%.2fs keys=[%s]",
                selected.index + 1,
                key_count,
                best_wait,
                status_text,
            )
            return selected, best_wait

    async def _call_registration(self, value: str) -> Fr24Response:
        result = await self._call({"registrations": value})
        if result.error and self.is_param_error(result.error):
            alt = await self._call({"registration": value})
            if not alt.error:
                return alt
            if alt.error and self.is_param_error(alt.error):
                alt2 = await self._call({"reg": value})
                if not alt2.error:
                    return alt2
        return result

    @staticmethod
    def _format_key_statuses(
        self,
        statuses: list[tuple[_KeyState, dict | None, float, bool, float | None]],
        now: float,
    ) -> str:
        parts: list[str] = []
        for key, snapshot, wait_for, is_parked, parked_until in statuses:
            if is_parked:
                parked_in = None
                if parked_until:
                    parked_in = max(0.0, parked_until - now)
                parts.append(
                    "key%s parked_in=%.2fs requests=%s"
                    % (
                        key.index + 1,
                        parked_in or 0.0,
                        key.requests,
                    )
                )
                continue
            if snapshot is None:
                continue
            parts.append(
                "key%s wait=%.2fs next=%.2fs cooldown=%.2fs min=%.2fs recent=%s requests=%s"
                % (
                    key.index + 1,
                    wait_for,
                    snapshot["next_in"],
                    snapshot["cooldown_in"],
                    snapshot["min_interval"],
                    snapshot["recent"],
                    key.requests,
                )
            )
        return "; ".join(parts)

    async def _call(self, params: dict) -> Fr24Response:
        active_count = await self.active_key_count()
        if active_count <= 0:
            retry_after = await self.next_unpark_in()
            return Fr24Response(
                flights=[],
                credits=None,
                error="No active FR24 API keys available (all parked)",
                rate_limited=False,
                no_active_keys=True,
                retry_after_seconds=int(retry_after) if retry_after is not None else None,
            )
        if self._pool_limiter:
            waited = await self._pool_limiter.wait()
            pool_snapshot = await self._pool_limiter.snapshot()
            self._log.debug(
                "FR24 pool spacing: waited=%.2fs min_interval=%.2fs next_in=%.2fs",
                waited,
                pool_snapshot["min_interval"],
                pool_snapshot["next_in"],
            )
        try:
            key_state, _ = await self._select_key()
        except NoActiveKeysError as exc:
            return Fr24Response(
                flights=[],
                credits=None,
                error="No active FR24 API keys available (all parked)",
                rate_limited=False,
                no_active_keys=True,
                retry_after_seconds=(
                    int(exc.retry_after_seconds)
                    if exc.retry_after_seconds is not None
                    else None
                ),
            )
        await key_state.limiter.wait()
        key_state.requests += 1
        key_state.last_used = time.monotonic()

        def _sync_call() -> tuple[dict, Fr24Credits | None]:
            response = key_state.client.transport.request(
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
            self._log.debug("FR24 request: key=%s", key_state.index + 1)
            payload, credits = await asyncio.to_thread(_sync_call)
        except RateLimitError as exc:
            await key_state.limiter.cooldown(60)
            self._log.warning(
                "FR24 rate limit hit for key %s; backing off for 60 seconds",
                key_state.index + 1,
            )
            error = f"{type(exc).__name__}: {exc}"
            return Fr24Response(
                flights=[],
                credits=None,
                error=error,
                rate_limited=True,
                key_index=key_state.index,
                key_suffix=key_state.suffix,
            )
        except TransportError as exc:
            snapshot = await key_state.limiter.snapshot()
            self._log.exception(
                "FR24 transport error key=%s params=%s limiter=%s",
                key_state.index + 1,
                params,
                snapshot,
            )
            error = f"{type(exc).__name__}: {exc}"
            return Fr24Response(
                flights=[],
                credits=None,
                error=error,
                rate_limited=False,
                key_index=key_state.index,
                key_suffix=key_state.suffix,
            )
        except Exception as exc:
            self._log.exception(
                "FR24 request failed key=%s params=%s",
                key_state.index + 1,
                params,
            )
            error = f"{type(exc).__name__}: {exc}"
            return Fr24Response(
                flights=[],
                credits=None,
                error=error,
                rate_limited=False,
                key_index=key_state.index,
                key_suffix=key_state.suffix,
            )
        flights = _normalize_positions(payload)
        return Fr24Response(
            flights=flights,
            credits=credits,
            error=None,
            rate_limited=False,
            key_index=key_state.index,
            key_suffix=key_state.suffix,
        )

    async def close(self) -> None:
        for key in self._keys:
            await asyncio.to_thread(key.client.transport.close)


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

    @property
    def min_interval(self) -> float:
        return self._min_interval

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
