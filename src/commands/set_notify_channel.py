import re

import discord
from discord import app_commands


_CHANNEL_ID_RE = re.compile(r"^<#(\\d+)>$")


async def _resolve_text_channel(interaction: discord.Interaction, value: str) -> discord.TextChannel | None:
    if interaction.guild is None:
        return None

    raw = value.strip()
    channel_id = None
    match = _CHANNEL_ID_RE.match(raw)
    if match:
        channel_id = int(match.group(1))
    elif raw.isdigit():
        channel_id = int(raw)

    if channel_id:
        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await interaction.client.fetch_channel(channel_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                channel = None
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    name = raw.lstrip("#")
    matches = [ch for ch in interaction.guild.text_channels if ch.name.lower() == name.lower()]
    if len(matches) == 1:
        return matches[0]
    return None


def register(tree, db, config) -> None:
    @tree.command(name="set-notify-channel", description="Set the default notification channel for this guild.")
    @app_commands.describe(channel="Channel name, mention, or ID to use for notifications")
    async def set_notify_channel(interaction: discord.Interaction, channel: str) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        if interaction.user.id != config.bot_owner_id:
            await interaction.response.send_message("Only the bot owner can set the notify channel.", ephemeral=True)
            return

        resolved = await _resolve_text_channel(interaction, channel)
        if resolved is None:
            await interaction.response.send_message(
                "Channel not found. Use a #channel mention, channel ID, or exact channel name.",
                ephemeral=True,
            )
            return

        me = interaction.guild.me or interaction.guild.get_member(interaction.client.user.id)
        if me:
            perms = resolved.permissions_for(me)
            if not perms.send_messages:
                await interaction.response.send_message(
                    f"I don't have permission to send messages in {resolved.mention}.",
                    ephemeral=True,
                )
                return

        await db.set_guild_notify_channel(
            guild_id=str(interaction.guild_id),
            channel_id=str(resolved.id),
            updated_by=str(interaction.user.id),
        )
        await interaction.response.send_message(
            f"Notifications will be posted in {resolved.mention}.",
            ephemeral=True,
        )
