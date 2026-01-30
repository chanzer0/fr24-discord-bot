from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any

import discord
import httpx

from .fr24.grpc_live_feed import (
    build_flight_key,
    build_headers,
    fetch_batch,
    grpc_available,
    grpc_import_error,
)
from .notify import build_embed, build_fr24_link, build_view
from .typecards_data import load_all_icaos


def _chunked(values: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return [values]
    return [values[idx : idx + size] for idx in range(0, len(values), size)]


def _pick_first(data: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


def _format_content(role_id: str, icao: str, flight: dict[str, Any]) -> str:
    callsign = _pick_first(flight, ["callsign", "flight_number", "flight"])
    if callsign:
        return f"<@&{role_id}> Missing type card {icao}: {callsign}"
    return f"<@&{role_id}> Missing type card {icao}"


def _load_models_from_file(path: str) -> set[str]:
    log = logging.getLogger(__name__)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return set()
    except Exception as exc:
        log.warning("Failed to read models file %s: %s", path, exc)
        return set()

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return set()
    codes: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = row.get("icao") or row.get("id")
        if not value:
            continue
        cleaned = str(value).strip().upper()
        if cleaned:
            codes.add(cleaned)
    return codes




async def _resolve_channel(bot, channel_id: str, cache: dict[str, discord.abc.Messageable]):
    cached = cache.get(channel_id)
    if cached is not None:
        return cached
    channel = bot.get_channel(int(channel_id))
    if channel is None:
        channel = await bot.fetch_channel(int(channel_id))
    cache[channel_id] = channel
    return channel


async def _send_typecard_alert(
    *,
    bot,
    channel_id: str,
    role_id: str,
    icao: str,
    flight: dict[str, Any],
    config,
    channel_cache: dict[str, discord.abc.Messageable],
    allowed_mentions: discord.AllowedMentions,
) -> bool:
    log = logging.getLogger(__name__)
    try:
        channel = await _resolve_channel(bot, channel_id, channel_cache)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to resolve channel %s: %s", channel_id, exc)
        return False

    embed = build_embed(
        flight,
        "aircraft",
        icao,
        credits_consumed=None,
        credits_remaining=None,
        api_key_suffix=None,
    )
    url = build_fr24_link(flight, config.fr24_web_base_url)
    view = build_view(
        url,
        db=None,
        guild_id="",
        sub_type="",
        codes=[],
        display_code="",
    )

    try:
        content = _format_content(role_id, icao, flight)
        await channel.send(
            content=content,
            embed=embed,
            view=view,
            allowed_mentions=allowed_mentions,
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to send typecards alert to channel %s: %s", channel_id, exc)
        return False
    return True


async def _notify_typecards_error(
    bot,
    channel_map: dict[str, str],
    owner_ids: list[int],
    guild_ids: set[str],
    message: str,
) -> None:
    log = logging.getLogger(__name__)
    if not guild_ids or not owner_ids:
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
            content = f"{mentions} Typecards poller error: {text}".strip()
            await channel.send(content=content)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
            log.warning(
                "Failed to send typecards poller error to guild %s channel %s: %s",
                guild_id,
                channel_id,
                exc,
            )


async def typecards_poll_once(bot, db, config, reference_data) -> dict | None:
    log = logging.getLogger(__name__)
    targets = await db.fetch_guild_typecard_targets()
    targets = [
        target
        for target in targets
        if target.get("notify_channel_id") and target.get("typecards_role_id")
    ]
    if not targets:
        log.info("Typecards poll skipped (no guilds with typecards role)")
        return None

    icao_path = config.typecards_icao_list_path.strip() or None
    all_icaos = load_all_icaos(icao_path)
    if not all_icaos:
        log.warning("Typecards poll skipped (ICAO list empty)")
        return None
    log.info("Typecards master list loaded (total=%s)", len(all_icaos))

    missing_icaos = all_icaos
    if await reference_data.has_models():
        before = len(all_icaos)
        missing_icaos = await reference_data.filter_missing_models(all_icaos)
        removed = before - len(missing_icaos)
        if removed:
            log.info(
                "Typecards list filtered (known=%s missing=%s)",
                removed,
                len(missing_icaos),
            )
    else:
        known = _load_models_from_file("models.json")
        if known:
            before = len(all_icaos)
            missing_icaos = [code for code in all_icaos if code not in known]
            removed = before - len(missing_icaos)
            if removed:
                log.info(
                    "Typecards list filtered via models.json (known=%s missing=%s)",
                    removed,
                    len(missing_icaos),
                )
        else:
            log.info(
                "Typecards models cache empty and models.json missing; using full list"
            )
    if not missing_icaos:
        log.warning("Typecards poll skipped (no missing ICAOs after filtering)")
        return None

    headers = build_headers()
    batches = _chunked(missing_icaos, max(1, config.typecards_batch_size))
    total_batches = len(batches)

    allowed_mentions = discord.AllowedMentions(roles=True, users=False, everyone=False)
    channel_cache: dict[str, discord.abc.Messageable] = {}

    total_matches = 0
    total_alerts = 0
    total_errors = 0

    async with httpx.AsyncClient(timeout=config.typecards_timeout_seconds) as client:
        for idx, batch in enumerate(batches):
            if idx > 0:
                delay = max(0.0, config.typecards_request_delay_seconds)
                jitter = (
                    random.uniform(0.0, config.typecards_jitter_seconds)
                    if config.typecards_jitter_seconds > 0
                    else 0.0
                )
                if delay > 0 or jitter > 0:
                    await asyncio.sleep(max(0.0, delay + jitter))

            payloads = await fetch_batch(
                client=client,
                icaos=batch,
                feed_limit=config.typecards_feed_limit,
                headers=headers,
            )

            ok_count = sum(1 for payload in payloads.values() if payload.get("ok"))
            err_count = len(batch) - ok_count
            matches = sum(payload.get("matched_count", 0) for payload in payloads.values())
            total_matches += matches
            total_errors += err_count
            err_suffix = f" | errors={err_count}" if err_count else ""
            log.info(
                "Typecards batch [%s/%s] size=%s ok=%s%s matches=%s",
                idx + 1,
                total_batches,
                len(batch),
                ok_count,
                err_suffix,
                matches,
            )

            for icao in batch:
                flights = payloads[icao].get("flights") or []
                if not flights:
                    continue
                for flight in flights:
                    flight_key = build_flight_key(flight)
                    if not flight_key:
                        continue
                    for target in targets:
                        guild_id = target.get("guild_id")
                        channel_id = target.get("notify_channel_id")
                        role_id = target.get("typecards_role_id")
                        if not guild_id or not channel_id or not role_id:
                            continue
                        already_logged = await db.typecard_notification_logged(
                            str(guild_id), icao, str(flight_key)
                        )
                        if already_logged:
                            continue
                        sent = await _send_typecard_alert(
                            bot=bot,
                            channel_id=str(channel_id),
                            role_id=str(role_id),
                            icao=icao,
                            flight=flight,
                            config=config,
                            channel_cache=channel_cache,
                            allowed_mentions=allowed_mentions,
                        )
                        if sent:
                            total_alerts += 1
                            await db.log_typecard_notification(
                                str(guild_id), icao, str(flight_key)
                            )

    return {
        "icaos": len(missing_icaos),
        "batches": total_batches,
        "matches": total_matches,
        "alerts": total_alerts,
        "errors": total_errors,
    }


async def typecards_poll_loop(bot, db, config, reference_data) -> None:
    log = logging.getLogger(__name__)
    if not grpc_available():
        log.error(
            "Typecards poller disabled: missing fr24 gRPC modules (%s)",
            grpc_import_error(),
        )
        return
    log.info(
        "Typecards poll loop started (interval=%ss batch=%s delay=%ss jitter=%ss)",
        config.typecards_poll_interval_seconds,
        config.typecards_batch_size,
        config.typecards_request_delay_seconds,
        config.typecards_jitter_seconds,
    )
    while True:
        cycle_started = time.monotonic()
        try:
            metrics = await typecards_poll_once(bot, db, config, reference_data)
            if metrics:
                log.info(
                    "Typecards poll complete: icaos=%s batches=%s matches=%s alerts=%s errors=%s",
                    metrics.get("icaos"),
                    metrics.get("batches"),
                    metrics.get("matches"),
                    metrics.get("alerts"),
                    metrics.get("errors"),
                )
        except Exception as exc:
            log.exception("Typecards poll loop failed")
            try:
                channel_map = await db.fetch_guild_channels()
                await _notify_typecards_error(
                    bot,
                    channel_map,
                    config.bot_owner_ids,
                    set(channel_map.keys()),
                    f"Typecards poll loop failed: {type(exc).__name__}: {exc}",
                )
            except Exception:
                log.exception("Failed to send typecards poller error notification")
        elapsed = time.monotonic() - cycle_started
        sleep_for = max(0.0, config.typecards_poll_interval_seconds - elapsed)
        await asyncio.sleep(sleep_for)
