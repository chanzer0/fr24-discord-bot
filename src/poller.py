from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from math import ceil
from math import asin, cos, radians, sin, sqrt

import discord

from .notify import build_embed, build_fr24_link, build_view


async def _resolve_airport_codes(
    code: str, reference_data
) -> tuple[str, str, set[str]] | None:
    value = code.strip().upper()
    if not value:
        return None
    if len(value) == 3:
        ref = await reference_data.get_airport_by_iata(value)
        if ref:
            preferred = ref.iata or ref.icao or value
            match_codes = {ref.icao, ref.iata}
            return preferred, preferred, {code for code in match_codes if code}
        return (value, value, {value}) if value.isalpha() else None
    if len(value) == 4:
        ref = await reference_data.get_airport(value)
        if ref:
            preferred = ref.iata or ref.icao or value
            match_codes = {ref.icao, ref.iata}
            return preferred, preferred, {code for code in match_codes if code}
        return (value, value, {value}) if value.isalpha() else None
    if len(value) == 2 and value.isalpha():
        return value, value, {value}
    return None


def _chunked(values: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return [values]
    return [values[idx : idx + size] for idx in range(0, len(values), size)]


def _extract_destination_codes(flight: dict) -> set[str]:
    keys = (
        "dest_iata",
        "destination_iata",
        "dest_icao",
        "destination_icao",
        "destination",
        "dest",
    )
    codes = set()
    for key in keys:
        value = flight.get(key)
        if not value:
            continue
        code = str(value).strip().upper()
        if code:
            codes.add(code)
    return codes


def _extract_origin_codes(flight: dict) -> set[str]:
    keys = (
        "orig_iata",
        "origin_iata",
        "orig_icao",
        "origin_icao",
        "origin",
        "orig",
    )
    codes = set()
    for key in keys:
        value = flight.get(key)
        if not value:
            continue
        code = str(value).strip().upper()
        if code:
            codes.add(code)
    return codes


def _extract_aircraft_code(flight: dict) -> str | None:
    keys = ("type", "aircraft_type", "aircraft", "model")
    for key in keys:
        value = flight.get(key)
        if not value:
            continue
        code = str(value).strip().upper()
        if code:
            return code
    return None


def _key_suffix(value: str | None) -> str:
    if not value:
        return "????"
    cleaned = str(value).strip()
    return cleaned[-4:] if cleaned else "????"


def _format_key_credits(
    credits_by_suffix: dict[str, dict] | None,
    key_suffixes: list[str],
    cycle_used_by_suffix: dict[str, int] | None = None,
) -> str:
    if not key_suffixes:
        return "none"
    parts: list[str] = []
    for suffix in key_suffixes:
        masked = f"***{suffix}"
        row = credits_by_suffix.get(suffix) if credits_by_suffix else None
        used = cycle_used_by_suffix.get(suffix) if cycle_used_by_suffix else None
        if not row:
            if used is None:
                parts.append(f"{masked}=n/a")
            else:
                parts.append(f"{masked}=c{used}")
            continue
        remaining = row.get("remaining")
        if remaining is None and used is None:
            parts.append(f"{masked}=n/a")
        elif remaining is not None and used is not None:
            parts.append(f"{masked}=r{remaining} c{used}")
        elif remaining is not None:
            parts.append(f"{masked}=r{remaining}")
        else:
            parts.append(f"{masked}=c{used}")
    return " ".join(parts)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(a)))
    return radius_km * c


def _parse_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_first_numeric(flight: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _parse_float(flight.get(key))
        if value is not None:
            return value
    return None


def _get_flight_position(flight: dict) -> tuple[float, float] | None:
    lat = _parse_float(flight.get("lat"))
    lon = _parse_float(flight.get("lon"))
    if lat is None or lon is None:
        return None
    return lat, lon


def _is_on_ground_like(flight: dict) -> bool:
    altitude = _get_first_numeric(flight, ("altitude", "altitude_ft", "alt"))
    speed = _get_first_numeric(flight, ("ground_speed", "speed", "speed_kts", "gspeed"))
    if altitude is None or speed is None:
        return False
    if altitude > 200 or speed > 30:
        return False
    vspeed = _get_first_numeric(flight, ("vspeed", "vertical_speed", "vertical_speed_fpm"))
    if vspeed is not None and abs(vspeed) > 200:
        return False
    return True


def _is_stationary_zero(flight: dict) -> bool:
    altitude = _get_first_numeric(flight, ("altitude", "altitude_ft", "alt"))
    speed = _get_first_numeric(flight, ("ground_speed", "speed", "speed_kts", "gspeed"))
    altitude_zero = altitude is None or altitude == 0
    speed_zero = speed is None or speed == 0
    return altitude_zero and speed_zero


async def _resolve_airport_from_codes(codes: set[str], reference_data):
    for code in codes:
        if len(code) == 3:
            ref = await reference_data.get_airport_by_iata(code)
        elif len(code) == 4:
            ref = await reference_data.get_airport(code)
        else:
            ref = None
        if ref:
            return ref
    return None


def _parse_eta(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_eta(flight: dict) -> datetime | None:
    for key in ("eta", "estimated_arrival", "eta_utc"):
        parsed = _parse_eta(flight.get(key))
        if parsed:
            return parsed
    return None


async def _is_airport_alert_eligible(flight: dict, reference_data) -> bool:
    dest_codes = _extract_destination_codes(flight)
    origin_codes = _extract_origin_codes(flight)
    if dest_codes and origin_codes and dest_codes.intersection(origin_codes):
        return not _is_stationary_zero(flight)

    dest_ref = await _resolve_airport_from_codes(dest_codes, reference_data)
    origin_ref = await _resolve_airport_from_codes(origin_codes, reference_data)
    if dest_ref and origin_ref and dest_ref.icao == origin_ref.icao:
        return not _is_stationary_zero(flight)

    if not _is_on_ground_like(flight):
        return True
    position = _get_flight_position(flight)
    if not position or not dest_ref or dest_ref.lat is None or dest_ref.lon is None:
        return True

    distance_km = _haversine_km(position[0], position[1], dest_ref.lat, dest_ref.lon)
    if distance_km > 10.0:
        return True

    eta = _extract_eta(flight)
    if eta:
        now = datetime.now(timezone.utc)
        if (eta - now).total_seconds() >= 30 * 60:
            return True

    return False

async def poll_loop(bot, db, fr24, config, poller_state, reference_data) -> None:
    log = logging.getLogger(__name__)
    log.info("Poll loop started")
    while True:
        await poller_state.wait_until_enabled()
        cycle_started = time.monotonic()
        metrics: dict | None = None
        try:
            metrics = await poll_once(bot, db, fr24, config, reference_data)
        except Exception as exc:
            log.exception("Poll loop failed")
            try:
                channel_map = await db.fetch_guild_channels()
                await _notify_poll_error(
                    bot,
                    channel_map,
                    config.bot_owner_ids,
                    set(channel_map.keys()),
                    f"Poll loop failed: {type(exc).__name__}: {exc}",
                )
            except Exception:
                log.exception("Failed to send poller error notification")
        elapsed = time.monotonic() - cycle_started
        base_sleep = max(0.0, poller_state.interval_seconds - elapsed)
        sleep_for = base_sleep + random.uniform(0, config.poll_jitter_seconds)
        if metrics:
            aircraft_counts = metrics.get("aircraft_icao_counts") or []
            aircraft_counts_text = ", ".join(aircraft_counts) if aircraft_counts else "none"
            airport_counts = metrics.get("airport_code_counts") or []
            airport_counts_text = ", ".join(airport_counts) if airport_counts else "none"
            credits_text = _format_key_credits(
                metrics.get("fr24_key_credits") or {},
                [_key_suffix(key) for key in config.fr24_api_keys],
                metrics.get("fr24_key_used") or {},
            )
            log.info(
                "Poll end [dur=%.1fs sleep=%.1fs] [air=%s] [apt=%s] [credits %s]",
                elapsed,
                sleep_for,
                aircraft_counts_text,
                airport_counts_text,
                credits_text,
            )
        await poller_state.sleep(sleep_for)


async def poll_once(bot, db, fr24, config, reference_data) -> dict | None:
    log = logging.getLogger(__name__)
    subs = await db.fetch_subscriptions()
    if not subs:
        log.info("Poll cycle skipped (no subscriptions)")
        return
    fr24.reset_cycle_stats()
    api_key_count = max(1, len(config.fr24_api_keys))
    effective_request_delay_seconds = (
        0.0 if api_key_count > 1 else config.fr24_request_delay_seconds
    )
    delay_text = (
        "0s" if effective_request_delay_seconds <= 0 else f"{effective_request_delay_seconds:.2f}s"
    )

    aircraft_icao_counts: dict[str, int] = {}
    aircraft_icao_order: list[str] = []
    airport_code_counts: dict[str, int] = {}
    airport_code_order: list[str] = []
    credits_remaining: int | None = None
    key_credits: dict[str, dict] = {}
    key_cycle_used: dict[str, int] = {}
    key_last_remaining: dict[str, int] = {}
    key_last_consumed: dict[str, int] = {}
    key_start_remaining: dict[str, int] = {}
    key_start_consumed: dict[str, int] = {}

    try:
        key_rows = await db.get_fr24_key_credits()
    except Exception:
        log.debug("Failed to load cached FR24 key credits for cycle", exc_info=True)
        key_rows = []
    for row in key_rows:
        suffix = row.get("key_suffix")
        if not suffix:
            continue
        remaining = row.get("remaining")
        consumed = row.get("consumed")
        if remaining is not None:
            key_start_remaining[suffix] = remaining
        if consumed is not None:
            key_start_consumed[suffix] = consumed

    def _track_aircraft_codes(flights: list[dict]) -> None:
        for flight in flights:
            if not flight:
                continue
            aircraft_code = _extract_aircraft_code(flight)
            if not aircraft_code:
                continue
            if aircraft_code in aircraft_icao_counts:
                aircraft_icao_counts[aircraft_code] += 1
            else:
                aircraft_icao_counts[aircraft_code] = 1
                aircraft_icao_order.append(aircraft_code)

    def _note_credits(credits) -> None:
        nonlocal credits_remaining
        if not credits or credits.remaining is None:
            return
        credits_remaining = credits.remaining

    def _note_airport_code(code: str, count: int) -> None:
        if not code or count <= 0:
            return
        normalized = str(code).strip().upper()
        if len(normalized) < 3:
            return
        if normalized in airport_code_counts:
            airport_code_counts[normalized] += count
        else:
            airport_code_counts[normalized] = count
            airport_code_order.append(normalized)

    def _note_key_credit_delta(key_suffix: str, credits) -> None:
        if not key_suffix or not credits:
            return
        used = 0
        if credits.remaining is not None:
            prev = key_last_remaining.get(key_suffix)
            if prev is None:
                prev = key_start_remaining.get(key_suffix)
            if prev is not None:
                delta = prev - credits.remaining
                if delta > 0:
                    used = delta
            key_last_remaining[key_suffix] = credits.remaining
        elif credits.consumed is not None:
            prev = key_last_consumed.get(key_suffix)
            if prev is None:
                prev = key_start_consumed.get(key_suffix)
            if prev is not None:
                delta = credits.consumed - prev
                if delta > 0:
                    used = delta
            key_last_consumed[key_suffix] = credits.consumed
        if used:
            key_cycle_used[key_suffix] = key_cycle_used.get(key_suffix, 0) + used
        elif key_suffix not in key_cycle_used:
            key_cycle_used[key_suffix] = 0

    channel_map = await db.fetch_guild_channels()
    aircraft_groups: dict[str, list[dict]] = {}
    airport_targets: dict[str, dict] = {}
    airport_cache: dict[str, tuple[str, str, set[str]] | None] = {}
    for sub in subs:
        sub_type = sub["type"]
        code = sub["code"]
        if sub_type == "airport":
            if code not in airport_cache:
                airport_cache[code] = await _resolve_airport_codes(
                    code, reference_data
                )
            resolved = airport_cache[code]
            if not resolved:
                log.warning(
                    "Skipping airport code %s (invalid format for FR24).",
                    code,
                )
                continue
            request_code, display_code, match_codes = resolved
            target = airport_targets.setdefault(
                request_code,
                {"display_code": display_code, "match_codes": set(), "subs": []},
            )
            target["match_codes"].update(match_codes)
            target["subs"].append(sub)
        else:
            aircraft_groups.setdefault(code, []).append(sub)

    batchable_codes = [
        code for code in airport_targets.keys() if len(code) in (3, 4)
    ]
    country_codes = [code for code in airport_targets.keys() if len(code) == 2]
    batches = _chunked(batchable_codes, config.fr24_airport_batch_size)
    aircraft_batches = _chunked(
        list(aircraft_groups.keys()),
        config.fr24_aircraft_batch_size,
    )

    unique_count = len(aircraft_groups) + len(airport_targets)
    total_requests = len(aircraft_batches) + len(country_codes) + len(batches)
    effective_max_requests_per_min = config.fr24_max_requests_per_min * api_key_count
    estimated_min_seconds = 0
    if total_requests:
        estimated_min_seconds = ceil(
            total_requests / max(1, effective_max_requests_per_min)
        ) * 60
    log.info(
        "Poll start [subs=%s uniq=%s req=%s] [air=%s apt=%s] [keys=%s rpm=%s delay=%s]",
        len(subs),
        unique_count,
        total_requests,
        len(aircraft_groups),
        len(airport_targets),
        api_key_count,
        config.fr24_max_requests_per_min,
        delay_text,
    )
    rate_limit_notified = False
    for batch in aircraft_batches:
        batch_subs = [sub for code in batch for sub in aircraft_groups.get(code, [])]
        log.debug(
            "Polling FR24 for aircraft batch=%s (%s subs)",
            ",".join(batch),
            len(batch_subs),
        )
        result = await fr24.fetch_by_aircraft_batch(batch)
        if result.error:
            if result.rate_limited:
                if not rate_limit_notified:
                    await _notify_poll_error(
                        bot,
                        channel_map,
                        config.bot_owner_ids,
                        {sub["guild_id"] for sub in batch_subs},
                        "FR24 rate limit hit for aircraft batch. Backing off for 60s.",
                    )
                    rate_limit_notified = True
                continue
            fallback_allowed = fr24.is_param_error(result.error)
            await _notify_poll_error(
                bot,
                channel_map,
                config.bot_owner_ids,
                {sub["guild_id"] for sub in batch_subs},
                f"FR24 request failed for aircraft batch {','.join(batch)}: {result.error}."
                + (" Falling back to per-code requests." if fallback_allowed else ""),
            )
            if not fallback_allowed:
                continue
            for aircraft_code in batch:
                entries = aircraft_groups.get(aircraft_code, [])
                if not entries:
                    continue
                log.debug(
                    "Fallback FR24 for aircraft %s (%s subs)",
                    aircraft_code,
                    len(entries),
                )
                fallback_result = await fr24.fetch_by_aircraft(aircraft_code)
                if fallback_result.error:
                    if fallback_result.rate_limited:
                        if not rate_limit_notified:
                            await _notify_poll_error(
                                bot,
                                channel_map,
                                config.bot_owner_ids,
                                {sub["guild_id"] for sub in entries},
                                f"FR24 rate limit hit for aircraft {aircraft_code}. Backing off for 60s.",
                            )
                            rate_limit_notified = True
                        continue
                    await _notify_poll_error(
                        bot,
                        channel_map,
                        config.bot_owner_ids,
                        {sub["guild_id"] for sub in entries},
                        f"FR24 request failed for aircraft {aircraft_code}: {fallback_result.error}",
                    )
                    continue

                flights = fallback_result.flights
                credits = fallback_result.credits
                _note_credits(credits)
                _track_aircraft_codes(flights)
                if credits and (credits.remaining is not None or credits.consumed is not None):
                    await db.set_fr24_credits(
                        remaining=credits.remaining,
                        consumed=credits.consumed,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                    if fallback_result.key_suffix:
                        await db.set_fr24_key_credits(
                            key_suffix=fallback_result.key_suffix,
                            remaining=credits.remaining,
                            consumed=credits.consumed,
                            updated_at=datetime.now(timezone.utc).isoformat(),
                        )
                        key_credits[fallback_result.key_suffix] = {
                            "remaining": credits.remaining,
                            "consumed": credits.consumed,
                        }
                        _note_key_credit_delta(fallback_result.key_suffix, credits)

                log.debug(
                    "FR24 response for aircraft %s: %s flights",
                    aircraft_code,
                    len(flights),
                )
                if flights:
                    log.debug(
                        "FR24 sample flight data for aircraft %s: %s",
                        aircraft_code,
                        json.dumps(flights[0], sort_keys=True, default=str),
                    )
                await _process_flights(
                    bot=bot,
                    db=db,
                    config=config,
                    channel_map=channel_map,
                    subscriptions=entries,
                    flights=flights,
                    sub_type="aircraft",
                    display_code=aircraft_code,
                    reference_data=reference_data,
                    credits=credits,
                    api_key_suffix=fallback_result.key_suffix,
                )

                if effective_request_delay_seconds > 0:
                    await asyncio.sleep(effective_request_delay_seconds)
            continue

        flights = result.flights
        credits = result.credits
        _note_credits(credits)
        if credits and (credits.remaining is not None or credits.consumed is not None):
            await db.set_fr24_credits(
                remaining=credits.remaining,
                consumed=credits.consumed,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            if result.key_suffix:
                await db.set_fr24_key_credits(
                    key_suffix=result.key_suffix,
                    remaining=credits.remaining,
                    consumed=credits.consumed,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
                key_credits[result.key_suffix] = {
                    "remaining": credits.remaining,
                    "consumed": credits.consumed,
                }
                _note_key_credit_delta(result.key_suffix, credits)

        log.debug(
            "FR24 response for aircraft batch %s: %s flights",
            ",".join(batch),
            len(flights),
        )
        if flights:
            log.debug(
                "FR24 sample flight data for aircraft batch %s: %s",
                ",".join(batch),
                json.dumps(flights[0], sort_keys=True, default=str),
            )

        flights_by_code: dict[str, list[dict]] = {code: [] for code in batch}
        for flight in flights:
            if not flight:
                continue
            aircraft_code = _extract_aircraft_code(flight)
            if not aircraft_code:
                continue
            if aircraft_code in aircraft_icao_counts:
                aircraft_icao_counts[aircraft_code] += 1
            else:
                aircraft_icao_counts[aircraft_code] = 1
                aircraft_icao_order.append(aircraft_code)
            if aircraft_code in flights_by_code:
                flights_by_code[aircraft_code].append(flight)

        for aircraft_code, matched_flights in flights_by_code.items():
            if not matched_flights:
                continue
            entries = aircraft_groups.get(aircraft_code, [])
            if not entries:
                continue
            await _process_flights(
                bot=bot,
                db=db,
                config=config,
                channel_map=channel_map,
                subscriptions=entries,
                flights=matched_flights,
                sub_type="aircraft",
                display_code=aircraft_code,
                reference_data=reference_data,
                credits=credits,
                api_key_suffix=result.key_suffix,
            )

        if effective_request_delay_seconds > 0:
            await asyncio.sleep(effective_request_delay_seconds)

    for batch in batches:
        batch_targets = [airport_targets[code] for code in batch if code in airport_targets]
        batch_subs = [sub for target in batch_targets for sub in target["subs"]]
        log.debug(
            "Polling FR24 for airports inbound=%s (%s subs)",
            ",".join(batch),
            len(batch_subs),
        )
        result = await fr24.fetch_by_airports_inbound(batch)
        if result.error:
            if result.rate_limited:
                if not rate_limit_notified:
                    await _notify_poll_error(
                        bot,
                        channel_map,
                        config.bot_owner_ids,
                        {sub["guild_id"] for sub in batch_subs},
                        "FR24 rate limit hit for airport batch. Backing off for 60s.",
                    )
                    rate_limit_notified = True
                continue
            fallback_allowed = fr24.is_param_error(result.error)
            await _notify_poll_error(
                bot,
                channel_map,
                config.bot_owner_ids,
                {sub["guild_id"] for sub in batch_subs},
                f"FR24 request failed for airport batch {','.join(batch)}: {result.error}."
                + (" Falling back to per-code requests." if fallback_allowed else ""),
            )
            if not fallback_allowed:
                continue
            for request_code in batch:
                target = airport_targets.get(request_code)
                if not target:
                    continue
                log.debug(
                    "Fallback FR24 for airport inbound=%s (%s subs)",
                    request_code,
                    len(target["subs"]),
                )
                fallback_result = await fr24.fetch_by_airport_inbound(request_code)
                if fallback_result.error:
                    if fallback_result.rate_limited:
                        if not rate_limit_notified:
                            await _notify_poll_error(
                                bot,
                                channel_map,
                                config.bot_owner_ids,
                                {sub["guild_id"] for sub in target["subs"]},
                                f"FR24 rate limit hit for airport {request_code}. Backing off for 60s.",
                            )
                            rate_limit_notified = True
                        continue
                    await _notify_poll_error(
                        bot,
                        channel_map,
                        config.bot_owner_ids,
                        {sub["guild_id"] for sub in target["subs"]},
                        f"FR24 request failed for airport {request_code}: {fallback_result.error}",
                    )
                    continue

                flights = fallback_result.flights
                credits = fallback_result.credits
                _note_credits(credits)
                _track_aircraft_codes(flights)
                if credits and (credits.remaining is not None or credits.consumed is not None):
                    await db.set_fr24_credits(
                        remaining=credits.remaining,
                        consumed=credits.consumed,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                    if fallback_result.key_suffix:
                        await db.set_fr24_key_credits(
                            key_suffix=fallback_result.key_suffix,
                            remaining=credits.remaining,
                            consumed=credits.consumed,
                            updated_at=datetime.now(timezone.utc).isoformat(),
                        )
                        key_credits[fallback_result.key_suffix] = {
                            "remaining": credits.remaining,
                            "consumed": credits.consumed,
                        }
                        _note_key_credit_delta(fallback_result.key_suffix, credits)

                log.debug(
                    "FR24 response for airport %s: %s flights",
                    request_code,
                    len(flights),
                )
                if flights:
                    log.debug(
                        "FR24 sample flight data for airport %s: %s",
                        request_code,
                        json.dumps(flights[0], sort_keys=True, default=str),
                    )
                await _process_flights(
                    bot=bot,
                    db=db,
                    config=config,
                    channel_map=channel_map,
                    subscriptions=target["subs"],
                    flights=flights,
                    sub_type="airport",
                    display_code=target["display_code"],
                    reference_data=reference_data,
                    credits=credits,
                    api_key_suffix=fallback_result.key_suffix,
                )

                if effective_request_delay_seconds > 0:
                    await asyncio.sleep(effective_request_delay_seconds)
            continue

        flights = result.flights
        credits = result.credits
        _note_credits(credits)
        if credits and (credits.remaining is not None or credits.consumed is not None):
            await db.set_fr24_credits(
                remaining=credits.remaining,
                consumed=credits.consumed,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            if result.key_suffix:
                await db.set_fr24_key_credits(
                    key_suffix=result.key_suffix,
                    remaining=credits.remaining,
                    consumed=credits.consumed,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
                key_credits[result.key_suffix] = {
                    "remaining": credits.remaining,
                    "consumed": credits.consumed,
                }
                _note_key_credit_delta(result.key_suffix, credits)

        log.debug(
            "FR24 response for airport batch %s: %s flights",
            ",".join(batch),
            len(flights),
        )
        if flights:
            log.debug(
                "FR24 sample flight data for airport batch %s: %s",
                ",".join(batch),
                json.dumps(flights[0], sort_keys=True, default=str),
            )

        match_map: dict[str, set[str]] = {}
        for request_code in batch:
            target = airport_targets.get(request_code)
            if not target:
                continue
            for match_code in target["match_codes"]:
                match_map.setdefault(match_code, set()).add(request_code)

        flights_by_code: dict[str, list[dict]] = {code: [] for code in batch}
        for flight in flights:
            if not flight:
                continue
            aircraft_code = _extract_aircraft_code(flight)
            if aircraft_code:
                if aircraft_code in aircraft_icao_counts:
                    aircraft_icao_counts[aircraft_code] += 1
                else:
                    aircraft_icao_counts[aircraft_code] = 1
                    aircraft_icao_order.append(aircraft_code)
            dest_codes = _extract_destination_codes(flight)
            matched = set()
            for dest_code in dest_codes:
                matched.update(match_map.get(dest_code, set()))
            if not matched:
                continue
            for request_code in matched:
                flights_by_code.setdefault(request_code, []).append(flight)
                target = airport_targets.get(request_code)
                if target:
                    _note_airport_code(target["display_code"], 1)

        for request_code, matched_flights in flights_by_code.items():
            if not matched_flights:
                continue
            target = airport_targets.get(request_code)
            if not target:
                continue
            await _process_flights(
                bot=bot,
                db=db,
                config=config,
                channel_map=channel_map,
                subscriptions=target["subs"],
                flights=matched_flights,
                sub_type="airport",
                display_code=target["display_code"],
                reference_data=reference_data,
                credits=credits,
                api_key_suffix=result.key_suffix,
            )

        if effective_request_delay_seconds > 0:
            await asyncio.sleep(effective_request_delay_seconds)

    for country_code in country_codes:
        target = airport_targets.get(country_code)
        if not target:
            continue
        log.debug(
            "Polling FR24 for airport country inbound=%s (%s subs)",
            country_code,
            len(target["subs"]),
        )
        result = await fr24.fetch_by_airport_inbound(country_code)
        if result.error:
            if result.rate_limited:
                if not rate_limit_notified:
                    await _notify_poll_error(
                        bot,
                        channel_map,
                        config.bot_owner_ids,
                        {sub["guild_id"] for sub in target["subs"]},
                        f"FR24 rate limit hit for airport country {country_code}. Backing off for 60s.",
                    )
                    rate_limit_notified = True
                continue
            await _notify_poll_error(
                bot,
                channel_map,
                config.bot_owner_ids,
                {sub["guild_id"] for sub in target["subs"]},
                f"FR24 request failed for airport country {country_code}: {result.error}",
            )
            continue

        flights = result.flights
        credits = result.credits
        _note_credits(credits)
        _track_aircraft_codes(flights)
        _note_airport_code(target["display_code"], len(flights))
        if credits and (credits.remaining is not None or credits.consumed is not None):
            await db.set_fr24_credits(
                remaining=credits.remaining,
                consumed=credits.consumed,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            if result.key_suffix:
                await db.set_fr24_key_credits(
                    key_suffix=result.key_suffix,
                    remaining=credits.remaining,
                    consumed=credits.consumed,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
                key_credits[result.key_suffix] = {
                    "remaining": credits.remaining,
                    "consumed": credits.consumed,
                }
                _note_key_credit_delta(result.key_suffix, credits)

        log.debug(
            "FR24 response for airport country %s: %s flights",
            country_code,
            len(flights),
        )
        if flights:
            log.debug(
                "FR24 sample flight data for airport country %s: %s",
                country_code,
                json.dumps(flights[0], sort_keys=True, default=str),
            )
        await _process_flights(
            bot=bot,
            db=db,
            config=config,
            channel_map=channel_map,
            subscriptions=target["subs"],
            flights=flights,
            sub_type="airport",
            display_code=target["display_code"],
            reference_data=reference_data,
            credits=credits,
            api_key_suffix=result.key_suffix,
        )

        if effective_request_delay_seconds > 0:
            await asyncio.sleep(effective_request_delay_seconds)

    key_stats = await fr24.snapshot_keys()
    return {
        "subscriptions": len(subs),
        "unique": unique_count,
        "requests": total_requests,
        "estimated_min_seconds": estimated_min_seconds,
        "fr24_key_stats": key_stats,
        "fr24_key_credits": key_credits,
        "fr24_key_used": key_cycle_used,
        "credits_remaining": credits_remaining,
        "aircraft_count": sum(aircraft_icao_counts.values()),
        "aircraft_icao_counts": [
            f"{code} ({aircraft_icao_counts[code]})" for code in aircraft_icao_order
        ],
        "airport_count": sum(airport_code_counts.values()),
        "airport_code_counts": [
            f"{code} ({airport_code_counts[code]})" for code in airport_code_order
        ],
    }


async def cleanup_loop(db, config) -> None:
    log = logging.getLogger(__name__)
    log.info("Cleanup loop started (retention_days=%s)", config.notification_retention_days)
    while True:
        cutoff = datetime.now(timezone.utc) - timedelta(days=config.notification_retention_days)
        deleted = await db.cleanup_notifications(cutoff.isoformat())
        if deleted:
            log.info("Cleaned %s notification log rows", deleted)
        await asyncio.sleep(24 * 60 * 60)


def _build_flight_id(flight: dict) -> str | None:
    for key in ("flight_id", "id", "fr24_id", "uuid"):
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


def _has_registration(flight: dict) -> bool:
    for key in ("registration", "reg"):
        value = flight.get(key)
        if value:
            return True
    return False


async def _process_flights(
    bot,
    db,
    config,
    channel_map: dict[str, str],
    subscriptions: list[dict],
    flights: list[dict],
    sub_type: str,
    display_code: str,
    reference_data,
    credits,
    api_key_suffix: str | None = None,
) -> None:
    if not flights:
        return

    subs_by_guild: dict[str, list[dict]] = {}
    for sub in subscriptions:
        subs_by_guild.setdefault(sub["guild_id"], []).append(sub)

    for flight in flights:
        if not flight:
            continue
        if sub_type == "aircraft":
            if not _has_registration(flight):
                continue
            if _is_stationary_zero(flight):
                continue
        if sub_type == "airport" and not await _is_airport_alert_eligible(flight, reference_data):
            continue
        flight_id = _build_flight_id(flight)
        if not flight_id:
            continue
        for guild_id, guild_subs in subs_by_guild.items():
            channel_id = channel_map.get(guild_id)
            if not channel_id:
                continue
            subscription_codes = sorted(
                {sub["code"] for sub in guild_subs if sub.get("code")}
            )
            subscription_ids = [sub["id"] for sub in guild_subs]
            already_logged = await db.fetch_logged_subscription_ids(
                flight_id, subscription_ids
            )
            to_notify = [sub for sub in guild_subs if sub["id"] not in already_logged]
            if not to_notify:
                continue
            user_ids = sorted({sub["user_id"] for sub in to_notify})
            sent = await _send_notification(
                bot=bot,
                db=db,
                config=config,
                channel_id=channel_id,
                guild_id=guild_id,
                user_ids=user_ids,
                flight=flight,
                sub_type=sub_type,
                display_code=display_code,
                credits=credits,
                api_key_suffix=api_key_suffix,
                subscription_codes=subscription_codes,
            )
            if sent:
                await db.log_notifications(
                    [sub["id"] for sub in to_notify],
                    flight_id,
                )


def _build_notification_content(user_ids: list[str], code: str, limit: int = 2000) -> str:
    base = f"Flight update for {code}"
    if not user_ids:
        return base
    mentions = [f"<@{user_id}>" for user_id in sorted(set(user_ids))]
    full = f"{' '.join(mentions)} - {base}"
    if len(full) <= limit:
        return full

    kept: list[str] = []
    total = len(mentions)
    for idx, mention in enumerate(mentions):
        remaining = total - (idx + 1)
        if remaining > 0:
            suffix = f" and {remaining} more - {base}"
        else:
            suffix = f" - {base}"
        candidate = f"{' '.join(kept + [mention])}{suffix}"
        if len(candidate) > limit:
            break
        kept.append(mention)

    if not kept:
        return base
    remaining = total - len(kept)
    if remaining > 0:
        content = f"{' '.join(kept)} and {remaining} more - {base}"
    else:
        content = f"{' '.join(kept)} - {base}"
    if len(content) > limit:
        return content[:limit]
    return content


async def _send_notification(
    bot,
    db,
    config,
    channel_id: str,
    guild_id: str,
    user_ids: list[str],
    flight: dict,
    sub_type: str,
    display_code: str,
    credits,
    api_key_suffix: str | None,
    subscription_codes: list[str],
) -> bool:
    log = logging.getLogger(__name__)
    try:
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(channel_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to resolve channel %s: %s", channel_id, exc)
        return False

    embed = build_embed(
        flight,
        sub_type,
        display_code,
        credits_consumed=getattr(credits, "consumed", None),
        credits_remaining=getattr(credits, "remaining", None),
        api_key_suffix=api_key_suffix,
    )
    url = build_fr24_link(flight, config.fr24_web_base_url)
    view = build_view(
        url,
        db=db,
        guild_id=guild_id,
        sub_type=sub_type,
        codes=subscription_codes,
        display_code=display_code,
    )

    try:
        content = _build_notification_content(user_ids, display_code)
        await channel.send(content=content, embed=embed, view=view)
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to send notification to channel %s: %s", channel_id, exc)
        return False
    return True




async def _notify_poll_error(
    bot,
    channel_map: dict[str, str],
    owner_ids: list[int],
    guild_ids: set[str],
    message: str,
) -> None:
    log = logging.getLogger(__name__)
    if not guild_ids:
        return
    if not owner_ids:
        return
    mentions = f"<@{owner_ids[0]}>"
    text = message.strip()
    if len(text) > 900:
        text = text[:897] + "..."
    for guild_id in guild_ids:
        channel_id = channel_map.get(guild_id)
        if not channel_id:
            continue
        try:
            channel = bot.get_channel(int(channel_id))
            if channel is None:
                channel = await bot.fetch_channel(int(channel_id))
            content = f"{mentions} Poller error: {text}".strip()
            await channel.send(content=content)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
            log.warning(
                "Failed to send poller error to guild %s channel %s: %s",
                guild_id,
                channel_id,
                exc,
            )
