    import discord


    def register(tree, db, config) -> None:
        @tree.command(name="help", description="Show command usage and tips.")
        async def help_command(interaction: discord.Interaction) -> None:
            message = (
                "Commands:
"
                "- /set-notify-channel <channel> (owner-only)
"
                "- /subscribe <aircraft|airport> <code>
"
                "- /unsubscribe <aircraft|airport> <code>

"
                "Notes:
"
                "- Aircraft codes are ICAO type designators like A388 or C172.
"
                "- Airport codes are ICAO codes like WAW.
"
                "- Notifications post to the guild's default channel.
"
                "- Polling interval and retention are configurable via env vars."
            )
            await interaction.response.send_message(message, ephemeral=True)
