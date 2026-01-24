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
        if sub_type not in ("aircraft", "airport", "registration"):
            return []
        codes = await db.fetch_user_subscription_codes(
            str(interaction.guild_id),
            str(interaction.user.id),
            sub_type,
        )
        value = current.strip().upper()
        if sub_type == "registration":
            value = value.replace(" ", "")
        if value:
            codes = [code for code in codes if value in code]
        choices = []
        for code in codes:
            label = code
            if sub_type == "aircraft":
                model = await reference_data.get_model(code)
                if model:
                    label = format_model_label(model)
            elif sub_type == "airport":
                if len(code) == 3:
                    airport = await reference_data.get_airport_by_iata(code)
                else:
                    airport = await reference_data.get_airport(code)
                if airport:
                    label = format_airport_label(airport)
            choices.append(app_commands.Choice(name=label, value=code))
            if len(choices) >= 25:
                break
        return choices

    @tree.command(
        name="unsubscribe",
        description="Unsubscribe from aircraft, registration, or inbound airport alerts.",
    )
    @app_commands.describe(subscription_type="Subscription type", code="Code")
    @app_commands.choices(
        subscription_type=[
            app_commands.Choice(name="aircraft", value="aircraft"),
            app_commands.Choice(name="registration", value="registration"),
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
                "Invalid code format. Codes must be at least 2 characters.",
                ephemeral=True,
            )
            return

        codes_to_try = [normalized]
        display_code = normalized
        if subscription_type.value == "airport":
            ref = None
            if len(normalized) == 3:
                ref = await reference_data.get_airport_by_iata(normalized)
            elif len(normalized) == 4:
                ref = await reference_data.get_airport(normalized)
            if ref:
                display_code = ref.iata or ref.icao or normalized
                preferred = display_code
                alternate = ref.icao if ref.icao and ref.icao != preferred else None
                codes_to_try = [preferred]
                if alternate and alternate not in codes_to_try:
                    codes_to_try.append(alternate)

        removed = False
        for candidate in codes_to_try:
            removed = await db.remove_subscription(
                guild_id=str(interaction.guild_id),
                user_id=str(interaction.user.id),
                sub_type=subscription_type.value,
                code=candidate,
            )
            if removed:
                break

        if removed:
            await interaction.response.send_message(
                f"Unsubscribed from {subscription_type.value} {display_code}.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"No subscription found for {subscription_type.value} {display_code}.",
                ephemeral=True,
            )
