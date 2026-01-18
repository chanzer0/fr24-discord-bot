import discord
from discord import app_commands

from ..validation import normalize_code


def register(tree, db, config) -> None:
    @tree.command(name="unsubscribe", description="Unsubscribe from aircraft or inbound airport alerts.")
    @app_commands.describe(subscription_type="Subscription type", code="ICAO code")
    @app_commands.choices(
        subscription_type=[
            app_commands.Choice(name="aircraft", value="aircraft"),
            app_commands.Choice(name="airport", value="airport"),
        ]
    )
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
