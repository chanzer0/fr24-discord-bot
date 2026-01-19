from datetime import datetime, timezone

import discord


def _format_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def register(tree, db, config) -> None:
    @tree.command(
        name="credits-remaining",
        description="Show the latest FR24 credits remaining value.",
    )
    async def credits_remaining(interaction: discord.Interaction) -> None:
        data = await db.get_fr24_credits()
        if not data:
            await interaction.response.send_message(
                "No FR24 credits data yet. It updates after the next FR24 API call.",
                ephemeral=True,
            )
            return

        remaining = data.get("remaining")
        consumed = data.get("consumed")
        updated_at = _format_timestamp(data.get("updated_at"))

        embed = discord.Embed(title="FR24 Credits", color=discord.Color.blurple())
        if remaining is not None:
            embed.add_field(name="Remaining", value=str(remaining), inline=True)
        if consumed is not None:
            embed.add_field(name="Consumed", value=str(consumed), inline=True)
        if updated_at:
            embed.add_field(name="Last Updated", value=updated_at, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
