import logging

import discord
from discord import app_commands


def register(tree, db, config) -> None:
    log = logging.getLogger(__name__)

    @tree.command(name="set-notify-channel", description="Set the default notification channel for this guild.")
    @app_commands.describe(channel="Channel to use for notifications")
    async def set_notify_channel(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        if interaction.user.id != config.bot_owner_id:
            await interaction.response.send_message("Only the bot owner can set the notify channel.", ephemeral=True)
            return

        me = interaction.guild.me or interaction.guild.get_member(interaction.client.user.id)
        if me:
            perms = channel.permissions_for(me)
            if not perms.send_messages:
                await interaction.response.send_message(
                    f"I don't have permission to send messages in {channel.mention}.",
                    ephemeral=True,
                )
                return

        await db.set_guild_notify_channel(
            guild_id=str(interaction.guild_id),
            channel_id=str(channel.id),
            updated_by=str(interaction.user.id),
        )
        await interaction.response.send_message(
            f"Notifications will be posted in {channel.mention}.",
            ephemeral=True,
        )

    @set_notify_channel.error
    async def set_notify_channel_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        data = getattr(interaction, "data", None)
        raw_options = None
        if isinstance(data, dict):
            raw_options = data.get("options")
        log.error(
            "set-notify-channel error: %s guild_id=%s user_id=%s channel_id=%s options=%s data=%s",
            error,
            interaction.guild_id,
            getattr(interaction.user, "id", None),
            getattr(interaction, "channel_id", None),
            raw_options,
            data,
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "I couldn't parse that channel. Try selecting from the channel picker and rerun the command.",
                ephemeral=True,
            )
