import discord


def register(tree, db, config) -> None:
    @tree.command(name="help", description="Show command usage and tips.")
    async def help_command(interaction: discord.Interaction) -> None:
        message = (
            "Commands:\n"
            "- /set-notify-channel <channel> (owner-only)\n"
            "- /subscribe <aircraft|airport> <code>\n"
            "- /unsubscribe <aircraft|airport> <code>\n"
            "- /refresh-reference <airports|models|all> (owner-only)\n\n"
            "Notes:\n"
            "- Aircraft codes are ICAO type designators like A388 or C172.\n"
            "- Airport codes are ICAO codes like WAW.\n"
            "- Notifications post to the guild's default channel.\n"
            "- Polling interval and retention are configurable via env vars."
        )
        await interaction.response.send_message(message, ephemeral=True)
