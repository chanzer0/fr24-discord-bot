import discord


def register(tree, db, config) -> None:
    @tree.command(name="help", description="Show command usage and tips.")
    async def help_command(interaction: discord.Interaction) -> None:
        message = (
            "Commands:\n"
            "- /subscribe <aircraft|airport> <code>\n"
            "- /unsubscribe <aircraft|airport> <code>\n"
            "- /my-subs\n"
            "- /credits-remaining\n"
            "- /help\n\n"
            "Owner-only commands:\n"
            "- /set-notify-channel <channel>\n"
            "- /refresh-reference <airports|models|all>\n"
            "- /logs\n"
            "- /start\n"
            "- /stop\n"
            "- /set-polling-interval <seconds>"
        )
        await interaction.response.send_message(message, ephemeral=True)
