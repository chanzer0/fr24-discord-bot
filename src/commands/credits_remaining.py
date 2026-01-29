from datetime import datetime, timezone

import discord


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: str | None) -> str | None:
    parsed = _parse_iso(value)
    if not parsed:
        return None
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def register(tree, db, config) -> None:
    @tree.command(
        name="credits-remaining",
        description="Show the latest FR24 credits remaining values.",
    )
    async def credits_remaining(interaction: discord.Interaction) -> None:
        rows = await db.get_fr24_key_credits()
        if not rows:
            await interaction.response.send_message(
                "No FR24 credits data yet. It updates after the next FR24 API call.",
                ephemeral=True,
            )
            return

        by_suffix = {row.get("key_suffix"): row for row in rows if row.get("key_suffix")}
        embed = discord.Embed(title="FR24 Credits (per key)", color=discord.Color.blurple())

        keys = []
        for key in config.fr24_api_keys:
            value = str(key).strip()
            suffix = value[-4:] if value else "????"
            keys.append(suffix)

        for idx, suffix in enumerate(keys, start=1):
            masked = f"***{suffix}"
            row = by_suffix.get(suffix)
            if not row:
                embed.add_field(
                    name=f"Key {idx} ({masked})",
                    value="No data yet",
                    inline=False,
                )
                continue
            remaining = row.get("remaining")
            consumed = row.get("consumed")
            updated_at = _format_timestamp(row.get("updated_at"))
            parked_until_dt = _parse_iso(row.get("parked_until"))
            parked_reason = row.get("parked_reason")
            parts = []
            if remaining is not None:
                parts.append(f"Remaining: {remaining}")
            if consumed is not None:
                parts.append(f"Consumed: {consumed}")
            if updated_at:
                parts.append(f"Updated: {updated_at}")
            if parked_until_dt and parked_until_dt > datetime.now(timezone.utc):
                parts.append(
                    f"Status: Parked until {parked_until_dt.strftime('%Y-%m-%d %H:%M UTC')}"
                )
                if parked_reason:
                    parts.append(f"Reason: {parked_reason}")
            embed.add_field(
                name=f"Key {idx} ({masked})",
                value=" | ".join(parts) if parts else "No data yet",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
