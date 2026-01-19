import logging
from dataclasses import dataclass

import discord
from discord import app_commands


@dataclass(frozen=True)
class ChannelRef:
    id: int
    name: str
    channel_type: discord.ChannelType
    permissions: discord.Permissions | None

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"


class ChannelRefTransformer(app_commands.Transformer):
    type = discord.AppCommandOptionType.channel

    async def transform(
        self, interaction: discord.Interaction, value: object
    ) -> ChannelRef:
        log = logging.getLogger(__name__)
        data = getattr(interaction, "data", {}) if interaction else {}
        options = data.get("options") if isinstance(data, dict) else None
        resolved_channels = None
        if isinstance(data, dict):
            resolved = data.get("resolved", {})
            resolved_channels = resolved.get("channels") if isinstance(resolved, dict) else None
        log.info(
            "set-notify-channel transform start value=%r type=%s guild_id=%s options=%s resolved_channel_ids=%s",
            value,
            type(value).__name__,
            getattr(interaction, "guild_id", None),
            options,
            list(resolved_channels.keys()) if isinstance(resolved_channels, dict) else None,
        )
        if hasattr(value, "id") and hasattr(value, "type"):
            channel_id = int(getattr(value, "id"))
            name = getattr(value, "name", str(channel_id))
            channel_type = getattr(value, "type")
            permissions_raw = getattr(value, "permissions", None)
            permissions = None
            if permissions_raw is not None:
                try:
                    permissions = discord.Permissions(int(permissions_raw))
                except (TypeError, ValueError):
                    permissions = None
            log.info("set-notify-channel transform: value is channel-like id=%s", channel_id)
            return ChannelRef(
                id=channel_id,
                name=name,
                channel_type=channel_type,
                permissions=permissions,
            )

        channel_id = None
        if isinstance(value, int):
            channel_id = value
        elif isinstance(value, str) and value.isdigit():
            channel_id = int(value)
        elif isinstance(value, dict):
            raw_id = value.get("id") or value.get("value")
            if raw_id and str(raw_id).isdigit():
                channel_id = int(raw_id)

        if channel_id is None and isinstance(data, dict):
            for opt in data.get("options", []):
                if opt.get("name") == "channel":
                    raw_value = opt.get("value")
                    if raw_value and str(raw_value).isdigit():
                        channel_id = int(raw_value)
                    break
        log.info("set-notify-channel transform: channel_id=%s", channel_id)

        if channel_id is not None:
            resolved = data.get("resolved") if isinstance(data, dict) else None
            if isinstance(resolved, dict):
                channels = resolved.get("channels", {})
                channel_data = channels.get(str(channel_id))
                if channel_data and channel_data.get("type") == 0:
                    log.info(
                        "set-notify-channel transform: resolved channel data name=%s type=%s",
                        channel_data.get("name"),
                        channel_data.get("type"),
                    )
                    permissions = None
                    permissions_raw = channel_data.get("permissions")
                    if permissions_raw is not None:
                        try:
                            permissions = discord.Permissions(int(permissions_raw))
                        except (TypeError, ValueError):
                            permissions = None
                    return ChannelRef(
                        id=channel_id,
                        name=channel_data.get("name", str(channel_id)),
                        channel_type=discord.ChannelType.text,
                        permissions=permissions,
                    )

        log.error(
            "set-notify-channel transform failed value=%r type=%s channel_id=%s",
            value,
            type(value).__name__,
            channel_id,
        )
        raise app_commands.TransformerError(value, self.type, self)


def register(tree, db, config) -> None:
    log = logging.getLogger(__name__)

    @tree.command(name="set-notify-channel", description="Set the default notification channel for this guild.")
    @app_commands.describe(channel="Channel to use for notifications")
    async def set_notify_channel(
        interaction: discord.Interaction,
        channel: app_commands.Transform[ChannelRef, ChannelRefTransformer],
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        if interaction.user.id != config.bot_owner_id:
            await interaction.response.send_message("Only the bot owner can set the notify channel.", ephemeral=True)
            return

        if channel.channel_type is not discord.ChannelType.text:
            await interaction.response.send_message(
                "Please select a text channel for notifications.",
                ephemeral=True,
            )
            return

        if channel.permissions and not channel.permissions.send_messages:
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
        error_value = None
        error_type = None
        if isinstance(error, app_commands.TransformerError):
            error_value = getattr(error, "value", None)
            error_type = getattr(error, "type", None)
        data = getattr(interaction, "data", None)
        raw_options = None
        if isinstance(data, dict):
            raw_options = data.get("options")
        log.error(
            "set-notify-channel error: %s value=%r value_type=%s option_type=%s guild_id=%s user_id=%s channel_id=%s options=%s data=%s",
            error,
            error_value,
            type(error_value).__name__ if error_value is not None else None,
            error_type,
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
