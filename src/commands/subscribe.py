import logging

import discord
from discord import app_commands

from ..reference_data import format_airport_label, format_model_label
from ..validation import normalize_code


def _resolve_subscription_type(interaction: discord.Interaction) -> str | None:
    namespace = getattr(interaction, "namespace", None)
    value = getattr(namespace, "subscription_type", None)
    if isinstance(value, app_commands.Choice):
        return value.value
    if isinstance(value, str):
        return value
    return None


def register(tree, db, config, reference_data) -> None:
    log = logging.getLogger(__name__)

    def _clean_name(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = value.strip()
        return cleaned or None

    async def _resolve_guild_name(interaction: discord.Interaction) -> str | None:
        guild = interaction.guild or interaction.client.get_guild(interaction.guild_id)
        name = _clean_name(getattr(guild, "name", None)) if guild else None
        if name:
            return name
        try:
            fetched = await interaction.client.fetch_guild(interaction.guild_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
            log.warning(
                "subscribe fetch_guild failed guild_id=%s error=%s",
                interaction.guild_id,
                exc,
            )
            return None
        return _clean_name(getattr(fetched, "name", None))

    async def code_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        sub_type = _resolve_subscription_type(interaction)
        if sub_type == "aircraft":
            models = await reference_data.search_models(current)
            return [
                app_commands.Choice(name=format_model_label(model), value=model.icao)
                for model in models
            ]
        if sub_type == "airport":
            airports = await reference_data.search_airports(current)
            return [
                app_commands.Choice(
                    name=format_airport_label(airport), value=airport.icao
                )
                for airport in airports
            ]
        return []

    @tree.command(name="subscribe", description="Subscribe to aircraft or inbound airport alerts.")
    @app_commands.describe(subscription_type="Subscription type", code="ICAO code")
    @app_commands.choices(
        subscription_type=[
            app_commands.Choice(name="aircraft", value="aircraft"),
            app_commands.Choice(name="airport", value="airport"),
        ]
    )
    @app_commands.autocomplete(code=code_autocomplete)
    async def subscribe(
        interaction: discord.Interaction,
        subscription_type: app_commands.Choice[str],
        code: str,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        settings = await db.get_guild_settings(str(interaction.guild_id))
        if not settings:
            await interaction.response.send_message(
                "No notification channel set. Ask the bot owner to run /set-notify-channel.",
                ephemeral=True,
            )
            return

        normalized = normalize_code(subscription_type.value, code)
        if not normalized:
            await interaction.response.send_message(
                "Invalid ICAO code format. Aircraft codes are 3-6 letters/numbers; airports are 4 letters.",
                ephemeral=True,
            )
            return

        guild_name = await _resolve_guild_name(interaction)
        user_name = _clean_name(
            getattr(interaction.user, "display_name", None) or interaction.user.name
        )
        log.info(
            "subscribe request guild_id=%s guild_name=%s user_id=%s user_name=%s type=%s code=%s",
            interaction.guild_id,
            guild_name,
            interaction.user.id,
            user_name,
            subscription_type.value,
            normalized,
        )
        inserted = await db.add_subscription(
            guild_id=str(interaction.guild_id),
            user_id=str(interaction.user.id),
            sub_type=subscription_type.value,
            code=normalized,
            guild_name=guild_name,
            user_name=user_name,
        )

        warning = None
        if subscription_type.value == "aircraft":
            found = await reference_data.get_model(normalized)
            if not found and await reference_data.has_models():
                warning = (
                    "Warning: that aircraft ICAO is not in the Skycards reference data."
                )
        else:
            found = await reference_data.get_airport(normalized)
            if not found and await reference_data.has_airports():
                warning = (
                    "Warning: that airport ICAO is not in the Skycards reference data."
                )

        if inserted:
            message = f"Subscribed to {subscription_type.value} {normalized}."
            if warning:
                message = f"{message}\n{warning}"
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.send_message(
                f"You are already subscribed to {subscription_type.value} {normalized}.",
                ephemeral=True,
            )
