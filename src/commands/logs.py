import discord
from discord import app_commands

from ..logs import format_log_block, read_log_tail


def register(tree, db, config) -> None:
    @tree.command(name="logs", description="Show recent bot logs (owner-only).")
    @app_commands.describe(
        lines="Number of lines to show (1-200)",
        contains="Filter lines by substring",
    )
    async def logs_command(
        interaction: discord.Interaction,
        lines: int = 50,
        contains: str | None = None,
    ) -> None:
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only bot owners can use this command.",
                ephemeral=True,
            )
            return

        lines = max(1, min(lines, 200))
        entries = read_log_tail(
            config.log_dir,
            lines=lines,
            contains=contains,
        )
        if not entries:
            await interaction.response.send_message(
                "No logs found.",
                ephemeral=True,
            )
            return

        text = format_log_block(entries, limit=1800)
        content = f"```\n{text}\n```"
        await interaction.response.send_message(content, ephemeral=True)
