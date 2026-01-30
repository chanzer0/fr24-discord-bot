import logging

import discord
from discord import app_commands


def register(tree, db, config) -> None:
    log = logging.getLogger(__name__)

    def _clean_name(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = value.strip()
        return cleaned or None

    @tree.command(
        name="set-type-cards-role",
        description="Set role to mention for missing type card alerts.",
    )
    @app_commands.describe(role="Role to mention for missing type card alerts")
    async def set_type_cards_role(
        interaction: discord.Interaction,
        role: discord.Role | None = None,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only a bot owner can set the type cards role.", ephemeral=True
            )
            return
        if role is None:
            await interaction.response.send_message(
                "Provide a role to update.", ephemeral=True
            )
            return

        settings = await db.get_guild_settings(str(interaction.guild_id))
        if not settings:
            await interaction.response.send_message(
                "No notification channel set. Run /set-notify-channel first.",
                ephemeral=True,
            )
            return

        user_name = _clean_name(
            getattr(interaction.user, "display_name", None) or interaction.user.name
        )

        role_id = str(role.id)
        role_name = _clean_name(role.name)

        log.debug(
            "set-type-cards-role guild_id=%s role_id=%s user_id=%s",
            interaction.guild_id,
            role_id,
            interaction.user.id,
        )

        await db.set_guild_typecards_role(
            guild_id=str(interaction.guild_id),
            role_id=role_id,
            role_name=role_name,
            updated_by=str(interaction.user.id),
            updated_by_name=user_name,
        )

        await interaction.response.send_message(
            f"Type cards role updated: <@&{role_id}>.",
            ephemeral=True,
        )
