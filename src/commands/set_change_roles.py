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
        name="set-change-roles",
        description="Set roles to mention for Skycards reference changes.",
    )
    @app_commands.describe(
        aircraft_role="Role to mention for aircraft/model changes",
        airport_role="Role to mention for airport changes",
    )
    async def set_change_roles(
        interaction: discord.Interaction,
        aircraft_role: discord.Role | None = None,
        airport_role: discord.Role | None = None,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only a bot owner can set change roles.", ephemeral=True
            )
            return
        if aircraft_role is None and airport_role is None:
            await interaction.response.send_message(
                "Provide at least one role to update.", ephemeral=True
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

        aircraft_role_id = str(aircraft_role.id) if aircraft_role else None
        aircraft_role_name = _clean_name(aircraft_role.name) if aircraft_role else None
        airport_role_id = str(airport_role.id) if airport_role else None
        airport_role_name = _clean_name(airport_role.name) if airport_role else None

        log.debug(
            "set-change-roles guild_id=%s aircraft_role_id=%s airport_role_id=%s user_id=%s",
            interaction.guild_id,
            aircraft_role_id,
            airport_role_id,
            interaction.user.id,
        )

        await db.set_guild_change_roles(
            guild_id=str(interaction.guild_id),
            aircraft_role_id=aircraft_role_id,
            aircraft_role_name=aircraft_role_name,
            airport_role_id=airport_role_id,
            airport_role_name=airport_role_name,
            updated_by=str(interaction.user.id),
            updated_by_name=user_name,
        )

        final_aircraft = (
            aircraft_role_id or settings.get("aircraft_change_role_id")
        )
        final_airport = airport_role_id or settings.get("airport_change_role_id")
        aircraft_text = f"<@&{final_aircraft}>" if final_aircraft else "none"
        airport_text = f"<@&{final_airport}>" if final_airport else "none"

        await interaction.response.send_message(
            f"Change roles updated. Aircraft/model: {aircraft_text}. Airport: {airport_text}.",
            ephemeral=True,
        )
