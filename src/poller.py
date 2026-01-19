from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from math import ceil

import discord

from .notify import build_embed, build_fr24_link, build_view


async def poll_loop(bot, db, fr24, config, poller_state) -> None:
    log = logging.getLogger(__name__)
    log.info("Poll loop started")
    while True:
        await poller_state.wait_until_enabled()
        cycle_started = time.monotonic()
        metrics: dict | None = None
        try:
            metrics = await poll_once(bot, db, fr24, config)
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
            log.info(
                "Poll cycle complete: subs=%s unique=%s duration=%.1fs sleep=%.1fs",
                metrics.get("subscriptions"),
                metrics.get("unique"),
                elapsed,
                sleep_for,
            )
        await poller_state.sleep(sleep_for)


async def poll_once(bot, db, fr24, config) -> dict | None:
    log = logging.getLogger(__name__)
    subs = await db.fetch_subscriptions()
    if not subs:
        log.info("Poll cycle skipped (no subscriptions)")
        return

    channel_map = await db.fetch_guild_channels()
    grouped: dict[tuple[str, str], list[dict]] = {}
    for sub in subs:
        key = (sub["type"], sub["code"])
        grouped.setdefault(key, []).append(sub)

    unique_count = len(grouped)
    estimated_min_seconds = 0
    if unique_count:
        estimated_min_seconds = ceil(
            unique_count / max(1, config.fr24_max_requests_per_min)
        ) * 60
    log.info(
        "Poll cycle start: subs=%s unique=%s min_cycle_seconds=%s max_requests_per_min=%s request_delay=%.1fs",
        len(subs),
        unique_count,
        estimated_min_seconds,
        config.fr24_max_requests_per_min,
        config.fr24_request_delay_seconds,
    )

    rate_limit_notified = False
    for (sub_type, code), entries in grouped.items():
        log.debug("Polling FR24 for %s %s (%s subs)", sub_type, code, len(entries))
        if sub_type == "aircraft":
            result = await fr24.fetch_by_aircraft(code)
        else:
            result = await fr24.fetch_by_airport_inbound(code)
        if result.error:
            if result.rate_limited:
                if not rate_limit_notified:
                    await _notify_poll_error(
                        bot,
                        channel_map,
                        config.bot_owner_ids,
                        {sub["guild_id"] for sub in entries},
                        f"FR24 rate limit hit for {sub_type} {code}. Backing off for 60s.",
                    )
                    rate_limit_notified = True
                continue
            else:
                await _notify_poll_error(
                    bot,
                    channel_map,
                    config.bot_owner_ids,
                    {sub["guild_id"] for sub in entries},
                    f"FR24 request failed for {sub_type} {code}: {result.error}",
                )
            continue

        flights = result.flights
        credits = result.credits
        if credits and (credits.remaining is not None or credits.consumed is not None):
            await db.set_fr24_credits(
                remaining=credits.remaining,
                consumed=credits.consumed,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

        log.debug("FR24 response for %s %s: %s flights", sub_type, code, len(flights))
        if flights:
            log.info(
                "FR24 sample flight data for %s %s: %s",
                sub_type,
                code,
                json.dumps(flights[0], sort_keys=True, default=str),
            )
        await _process_flights(
            bot=bot,
            db=db,
            config=config,
            channel_map=channel_map,
            subscriptions=entries,
            flights=flights,
            sub_type=sub_type,
            code=code,
            credits=credits,
        )

        if config.fr24_request_delay_seconds > 0:
            await asyncio.sleep(config.fr24_request_delay_seconds)

    return {
        "subscriptions": len(subs),
        "unique": unique_count,
        "estimated_min_seconds": estimated_min_seconds,
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


async def _process_flights(
    bot,
    db,
    config,
    channel_map: dict[str, str],
    subscriptions: list[dict],
    flights: list[dict],
    sub_type: str,
    code: str,
    credits,
) -> None:
    if not flights:
        return

    subs_by_guild: dict[str, list[dict]] = {}
    for sub in subscriptions:
        subs_by_guild.setdefault(sub["guild_id"], []).append(sub)

    for flight in flights:
        if not flight:
            continue
        flight_id = _build_flight_id(flight)
        if not flight_id:
            continue
        for guild_id, guild_subs in subs_by_guild.items():
            channel_id = channel_map.get(guild_id)
            if not channel_id:
                continue
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
                config=config,
                channel_id=channel_id,
                user_ids=user_ids,
                flight=flight,
                sub_type=sub_type,
                code=code,
                credits=credits,
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
    config,
    channel_id: str,
    user_ids: list[str],
    flight: dict,
    sub_type: str,
    code: str,
    credits,
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
        code,
        credits_consumed=getattr(credits, "consumed", None),
        credits_remaining=getattr(credits, "remaining", None),
    )
    url = build_fr24_link(flight, config.fr24_web_base_url)
    view = build_view(url)

    try:
        content = _build_notification_content(user_ids, code)
        await channel.send(content=content, embed=embed, view=view)
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to send notification to channel %s: %s", channel_id, exc)
        return False
    return True




async def _notify_poll_error(
    bot,
    channel_map: dict[str, str],
    owner_ids: set[int],
    guild_ids: set[str],
    message: str,
) -> None:
    log = logging.getLogger(__name__)
    if not guild_ids:
        return
    mentions = " ".join(f"<@{owner_id}>" for owner_id in sorted(owner_ids))
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
