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
    async def code_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild_id is None:
            return []
        sub_type = _resolve_subscription_type(interaction)
        if sub_type not in ("aircraft", "airport"):
            return []
        codes = await db.fetch_user_subscription_codes(
            str(interaction.guild_id),
            str(interaction.user.id),
            sub_type,
        )
        value = current.strip().upper()
        if value:
            codes = [code for code in codes if value in code]
        choices = []
        for code in codes:
            label = code
            if sub_type == "aircraft":
                model = await reference_data.get_model(code)
                if model:
                    label = format_model_label(model)
            else:
                airport = await reference_data.get_airport(code)
                if airport:
                    label = format_airport_label(airport)
            choices.append(app_commands.Choice(name=label, value=code))
            if len(choices) >= 25:
                break
        return choices

    @tree.command(name="unsubscribe", description="Unsubscribe from aircraft or inbound airport alerts.")
    @app_commands.describe(subscription_type="Subscription type", code="ICAO code")
    @app_commands.choices(
        subscription_type=[
            app_commands.Choice(name="aircraft", value="aircraft"),
            app_commands.Choice(name="airport", value="airport"),
        ]
    )
    @app_commands.autocomplete(code=code_autocomplete)
    async def unsubscribe(
        interaction: discord.Interaction,
        subscription_type: app_commands.Choice[str],
        code: str,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        normalized = normalize_code(subscription_type.value, code)
        if not normalized:
            await interaction.response.send_message(
                "Invalid ICAO code format. Aircraft codes are 3-6 letters/numbers; airports are 4 letters.",
                ephemeral=True,
            )
            return

        removed = await db.remove_subscription(
            guild_id=str(interaction.guild_id),
            user_id=str(interaction.user.id),
            sub_type=subscription_type.value,
            code=normalized,
        )

        if removed:
            await interaction.response.send_message(
                f"Unsubscribed from {subscription_type.value} {normalized}.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"No subscription found for {subscription_type.value} {normalized}.",
                ephemeral=True,
            )
