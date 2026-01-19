from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from datetime import datetime, timedelta, timezone

import discord

from .notify import build_embed, build_fr24_link, build_view


async def poll_loop(bot, db, fr24, config) -> None:
    log = logging.getLogger(__name__)
    log.info("Poll loop started")
    while True:
        try:
            await poll_once(bot, db, fr24, config)
        except Exception:
            log.exception("Poll loop failed")
        sleep_for = config.poll_interval_seconds + random.uniform(0, config.poll_jitter_seconds)
        await asyncio.sleep(sleep_for)


async def poll_once(bot, db, fr24, config) -> None:
    log = logging.getLogger(__name__)
    subs = await db.fetch_subscriptions()
    if not subs:
        return

    channel_map = await db.fetch_guild_channels()
    grouped: dict[tuple[str, str], list[dict]] = {}
    for sub in subs:
        key = (sub["type"], sub["code"])
        grouped.setdefault(key, []).append(sub)

    for (sub_type, code), entries in grouped.items():
        if sub_type == "aircraft":
            flights = await fr24.fetch_by_aircraft(code)
        else:
            flights = await fr24.fetch_by_airport_inbound(code)

        await _process_flights(
            bot=bot,
            db=db,
            config=config,
            channel_map=channel_map,
            subscriptions=entries,
            flights=flights,
            sub_type=sub_type,
            code=code,
        )

        if config.fr24_request_delay_seconds > 0:
            await asyncio.sleep(config.fr24_request_delay_seconds)

    log.info("Poll cycle complete")


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


async def _process_flights(
    bot,
    db,
    config,
    channel_map: dict[str, str],
    subscriptions: list[dict],
    flights: list[dict],
    sub_type: str,
    code: str,
) -> None:
    if not flights:
        return

    for flight in flights:
        if not flight:
            continue
        flight_id = _build_flight_id(flight)
        if not flight_id:
            continue
        for sub in subscriptions:
            channel_id = channel_map.get(sub["guild_id"])
            if not channel_id:
                continue
            already_sent = await db.notification_logged(sub["id"], flight_id)
            if already_sent:
                continue
            sent = await _send_notification(
                bot=bot,
                config=config,
                channel_id=channel_id,
                user_id=sub["user_id"],
                flight=flight,
                sub_type=sub_type,
                code=code,
            )
            if sent:
                await db.log_notification(sub["id"], flight_id)


async def _send_notification(bot, config, channel_id: str, user_id: str, flight: dict, sub_type: str, code: str) -> bool:
    log = logging.getLogger(__name__)
    try:
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(channel_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to resolve channel %s: %s", channel_id, exc)
        return False

    embed = build_embed(flight, sub_type, code)
    url = build_fr24_link(flight, config.fr24_web_base_url)
    view = build_view(url)

    try:
        await channel.send(content=f"<@{user_id}> Flight update for {code}", embed=embed, view=view)
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to send notification to channel %s: %s", channel_id, exc)
        return False
    return True
