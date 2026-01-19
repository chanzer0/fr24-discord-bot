import logging

import discord
from discord import app_commands


def register(tree, db, config, reference_data) -> None:
    log = logging.getLogger(__name__)

    @tree.command(
        name="refresh-reference",
        description="Refresh airport/model reference data used for autocomplete.",
    )
    @app_commands.describe(dataset="Which reference dataset to refresh")
    @app_commands.choices(
        dataset=[
            app_commands.Choice(name="airports", value="airports"),
            app_commands.Choice(name="models", value="models"),
            app_commands.Choice(name="all", value="all"),
        ]
    )
    async def refresh_reference(
        interaction: discord.Interaction,
        dataset: app_commands.Choice[str],
    ) -> None:
        if interaction.user.id not in config.bot_owner_ids:
            await interaction.response.send_message(
                "Only a bot owner can refresh reference data.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            results = await reference_data.refresh(dataset.value)
        except Exception as exc:
            log.exception("Reference refresh failed")
            await interaction.followup.send(
                f"Reference refresh failed: {exc}",
                ephemeral=True,
            )
            return

        lines = []
        for key in ("airports", "models"):
            if key not in results:
                continue
            entry = results[key]
            lines.append(
                f"{key}: {entry.get('rows')} rows (updated_at={entry.get('updated_at')}, fetched_at={entry.get('fetched_at')})"
            )
        message = "Reference refresh complete.\n" + "\n".join(lines)
        await interaction.followup.send(message, ephemeral=True)
