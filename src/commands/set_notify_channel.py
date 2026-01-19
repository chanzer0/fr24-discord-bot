import discord
from discord import app_commands


def register(tree, db, config) -> None:
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
