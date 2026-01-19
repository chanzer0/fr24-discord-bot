import discord
from discord import app_commands

from ..utils import utc_now_iso


def register(tree, db, config, poller_state) -> None:
    @tree.command(name="start", description="Start the FR24 polling loop.")
    async def start(interaction: discord.Interaction) -> None:
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only a bot owner can start polling.", ephemeral=True
            )
            return
        poller_state.set_enabled(True)
        await db.set_setting("polling_enabled", "1", utc_now_iso())
        await interaction.response.send_message(
            f"Polling started. Interval: {poller_state.interval_seconds} seconds.",
            ephemeral=True,
        )

    @tree.command(name="stop", description="Stop the FR24 polling loop.")
    async def stop(interaction: discord.Interaction) -> None:
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only a bot owner can stop polling.", ephemeral=True
            )
            return
        poller_state.set_enabled(False)
        await db.set_setting("polling_enabled", "0", utc_now_iso())
        await interaction.response.send_message(
            "Polling stopped. Current cycle (if running) will finish.",
            ephemeral=True,
        )

    @tree.command(
        name="set-polling-interval",
        description="Set the FR24 polling interval in seconds.",
    )
    @app_commands.describe(seconds="Polling interval in seconds")
    async def set_polling_interval(
        interaction: discord.Interaction, seconds: int
    ) -> None:
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only a bot owner can change the polling interval.", ephemeral=True
            )
            return
        if seconds < 1:
            await interaction.response.send_message(
                "Polling interval must be at least 1 second.",
                ephemeral=True,
            )
            return
        poller_state.set_interval(seconds)
        await db.set_setting("poll_interval_seconds", str(seconds), utc_now_iso())
        await interaction.response.send_message(
            f"Polling interval set to {seconds} seconds.",
            ephemeral=True,
        )
