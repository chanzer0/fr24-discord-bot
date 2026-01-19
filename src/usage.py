import asyncio
import io
import json
import logging
from datetime import datetime, time, timedelta, timezone

import discord

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for older envs
    ZoneInfo = None


_EASTERN_TZ = "America/New_York"


def _get_tz() -> timezone:
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(_EASTERN_TZ)
    except Exception:
        return timezone.utc


def _next_run_utc(now_utc: datetime) -> datetime:
    tz = _get_tz()
    if tz is timezone.utc:
        scheduled = datetime.combine(now_utc.date(), time(8, 0), tzinfo=timezone.utc)
        if now_utc >= scheduled:
            scheduled += timedelta(days=1)
        return scheduled
    local_now = now_utc.astimezone(tz)
    scheduled_local = datetime.combine(local_now.date(), time(8, 0), tzinfo=tz)
    if local_now >= scheduled_local:
        scheduled_local += timedelta(days=1)
    return scheduled_local.astimezone(timezone.utc)


def _find_value(data: dict, keys: list[str]) -> str | None:
    def _find_in_obj(obj, key):
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for value in obj.values():
                found = _find_in_obj(value, key)
                if found is not None:
                    return found
        return None

    for key in keys:
        value = _find_in_obj(data, key)
        if value is not None:
            return str(value)
    return None


def build_usage_embed(usage: dict, fetched_at: str | None) -> discord.Embed:
    embed = discord.Embed(
        title="FR24 API Usage",
        color=discord.Color.blurple(),
    )

    remaining = _find_value(usage, ["remaining", "remaining_credits", "credits_remaining"])
    used = _find_value(usage, ["used", "used_credits", "credits_used"])
    limit = _find_value(usage, ["limit", "credits", "monthly_limit", "total"])
    period_start = _find_value(usage, ["period_start", "start", "start_date"])
    period_end = _find_value(usage, ["period_end", "end", "end_date", "reset_at"])
    plan = _find_value(usage, ["plan", "tier", "subscription"])

    if remaining:
        embed.add_field(name="Remaining", value=remaining, inline=True)
    if used:
        embed.add_field(name="Used", value=used, inline=True)
    if limit:
        embed.add_field(name="Limit", value=limit, inline=True)
    if period_start:
        embed.add_field(name="Period Start", value=period_start, inline=True)
    if period_end:
        embed.add_field(name="Period End", value=period_end, inline=True)
    if plan:
        embed.add_field(name="Plan", value=plan, inline=True)

    if fetched_at:
        embed.add_field(name="Last Updated", value=fetched_at, inline=False)
        try:
            timestamp = datetime.fromisoformat(fetched_at)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            embed.timestamp = timestamp
            embed.set_footer(text="Usage cache timestamp")
        except ValueError:
            embed.set_footer(text="Usage cache timestamp unavailable")
    return embed


def build_usage_payload_message(usage: dict) -> tuple[str, discord.File | None]:
    payload = json.dumps(usage, indent=2, sort_keys=True, default=str)
    if len(payload) <= 1800:
        return f"```json\n{payload}\n```", None
    buffer = io.BytesIO(payload.encode("utf-8"))
    return "Usage payload attached as JSON.", discord.File(buffer, filename="fr24-usage.json")


async def broadcast_usage(bot, db, usage: dict, fetched_at: str) -> None:
    log = logging.getLogger(__name__)
    channels = await db.fetch_guild_channels()
    if not channels:
        log.info("Usage broadcast skipped: no notify channels configured")
        return

    embed = build_usage_embed(usage, fetched_at)
    sent = 0
    for guild_id, channel_id in channels.items():
        try:
            channel = bot.get_channel(int(channel_id))
            if channel is None:
                channel = await bot.fetch_channel(int(channel_id))
            await channel.send(content="FR24 API usage update", embed=embed)
            sent += 1
        except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
            log.warning(
                "Failed to send usage update to guild %s channel %s: %s",
                guild_id,
                channel_id,
                exc,
            )
    log.info("Usage broadcast complete: sent=%s channels=%s", sent, len(channels))


async def usage_loop(bot, db, fr24, config) -> None:
    log = logging.getLogger(__name__)
    tz = _get_tz()
    if tz is timezone.utc:
        log.info("Usage loop scheduled for 08:00 UTC (timezone data unavailable)")
    else:
        log.info("Usage loop scheduled for 08:00 %s", _EASTERN_TZ)

    while True:
        now = datetime.now(timezone.utc)
        next_run = _next_run_utc(now)
        wait_for = max(0, (next_run - now).total_seconds())
        log.info("Next usage report at %s", next_run.isoformat())
        await asyncio.sleep(wait_for)

        usage = await fr24.fetch_usage()
        if not usage:
            log.warning("FR24 usage fetch returned no data")
            await asyncio.sleep(60)
            continue

        fetched_at = datetime.now(timezone.utc).isoformat()
        await db.set_usage_cache(usage, fetched_at)
        log.info("Usage cache updated at %s", fetched_at)
        await broadcast_usage(bot, db, usage, fetched_at)
