from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands


_PARK_DURATION = timedelta(hours=24)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _mask_suffix(value: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        return "????"
    return cleaned[-4:]


def _suffix_for_index(config, index: int) -> str | None:
    if index < 1 or index > len(config.fr24_api_keys):
        return None
    return _mask_suffix(config.fr24_api_keys[index - 1])


def _build_key_choices(config, current: str) -> list[app_commands.Choice[int]]:
    query = str(current or "").strip().lower()
    choices: list[app_commands.Choice[int]] = []
    for idx, key in enumerate(config.fr24_api_keys, start=1):
        suffix = _mask_suffix(key)
        name = f"{idx}: ***{suffix}"
        if not query or query in name.lower() or query == str(idx):
            choices.append(app_commands.Choice(name=name, value=idx))
    return choices[:25]


def register(tree, db, config, fr24) -> None:
    async def _autocomplete_key_index(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        return _build_key_choices(config, current)

    @tree.command(name="park-key", description="Park an FR24 API key for 24 hours.")
    @app_commands.describe(key_index="FR24 API key index to park")
    @app_commands.autocomplete(key_index=_autocomplete_key_index)
    async def park_key(interaction: discord.Interaction, key_index: int) -> None:
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only a bot owner can park keys.",
                ephemeral=True,
            )
            return
        suffix = _suffix_for_index(config, key_index)
        if not suffix:
            await interaction.response.send_message(
                "Invalid key index.",
                ephemeral=True,
            )
            return
        now = datetime.now(timezone.utc)
        parked_until = now + _PARK_DURATION
        await db.set_fr24_key_parked(
            key_suffix=suffix,
            parked_until=parked_until.isoformat(),
            parked_reason="manual",
            parked_at=now.isoformat(),
            parked_notified_at=now.isoformat(),
        )
        await fr24.park_key_by_index(
            key_index - 1,
            parked_until.timestamp(),
            "manual",
        )
        await interaction.response.send_message(
            f"Key {key_index} (***{suffix}) parked until {_format_timestamp(parked_until)}.",
            ephemeral=True,
        )

    @tree.command(name="unpark-key", description="Unpark a parked FR24 API key.")
    @app_commands.describe(key_index="FR24 API key index to unpark")
    @app_commands.autocomplete(key_index=_autocomplete_key_index)
    async def unpark_key(interaction: discord.Interaction, key_index: int) -> None:
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only a bot owner can unpark keys.",
                ephemeral=True,
            )
            return
        suffix = _suffix_for_index(config, key_index)
        if not suffix:
            await interaction.response.send_message(
                "Invalid key index.",
                ephemeral=True,
            )
            return
        await db.clear_fr24_key_parked(suffix)
        await fr24.unpark_key_by_index(key_index - 1)
        await interaction.response.send_message(
            f"Key {key_index} (***{suffix}) unparked.",
            ephemeral=True,
        )
