from datetime import datetime, timedelta, timezone

import discord

from ..usage import build_usage_embed, build_usage_payload_message


_USAGE_REFRESH_WINDOW = timedelta(minutes=30)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def register(tree, db, config, fr24) -> None:
    @tree.command(name="usage", description="Show FR24 API usage statistics.")
    async def usage(interaction: discord.Interaction) -> None:
        now = datetime.now(timezone.utc)
        cached = await db.get_usage_cache()

        usage_payload = None
        fetched_at = None
        refresh_note = None

        if cached:
            fetched_at = cached.get("fetched_at")
            fetched_dt = _parse_timestamp(fetched_at)
            if fetched_dt and (now - fetched_dt) < _USAGE_REFRESH_WINDOW:
                usage_payload = cached.get("payload", {})
            else:
                refresh_note = "Cache older than 30 minutes; refreshing."
        else:
            refresh_note = "No cached usage; fetching now."

        if usage_payload is None:
            latest = await fr24.fetch_usage()
            if latest:
                usage_payload = latest
                fetched_at = now.isoformat()
                await db.set_usage_cache(usage_payload, fetched_at)
            elif cached:
                usage_payload = cached.get("payload", {})
                fetched_at = cached.get("fetched_at")
                refresh_note = "FR24 usage refresh failed; showing cached data."
            else:
                await interaction.response.send_message(
                    "Unable to fetch usage data right now. Please try again later.",
                    ephemeral=True,
                )
                return

        embed = build_usage_embed(usage_payload, fetched_at)
        content, attachment = build_usage_payload_message(usage_payload)

        if refresh_note:
            content = f"{refresh_note}\n{content}"

        if attachment:
            await interaction.response.send_message(
                content=content,
                embed=embed,
                file=attachment,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                content=content,
                embed=embed,
                ephemeral=True,
            )
