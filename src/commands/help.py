import discord


def register(tree, db, config) -> None:
    @tree.command(name="help", description="Show command usage and tips.")
    async def help_command(interaction: discord.Interaction) -> None:
        message = (
            "Commands:\n"
            "- /subscribe <aircraft|registration|airport> <code>\n"
            "- /unsubscribe <aircraft|registration|airport> <code>\n"
            "- /my-subs\n"
            "- /credits-remaining\n"
            "- /info <aircraft|airport> <code>\n"
            "- /reglist <field> <op> <value>\n"
            "  Rarity uses rareness/100 (A380 is 3.09). Weight uses tons (A380 is ~575).\n"
            '  Example: /reglist field="Rarity Tier" op="=" value="uncommon"\n'
            '  Example: /reglist field="Weight" op=">=" value="200"\n'
            '  Example: /reglist field="Wingspan" op="between" value="60..80"\n'
            '  Example: /reglist field="Num Engines" op="in" value="2,4"\n'
            '  Example: /reglist field="Manufacturers" op="contains" value="AIRBUS"\n'
            "  **NOTE**: Manufacturer autocomplete shows only values with 2+ aircraft; you can still type any manufacturer.\n"
            "  If more than 99 ICAO codes match, results are split into 99-per-line chunks for FR24.\n"
            '  Example: /reglist field="Military" op="is" value="true"\n'
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
