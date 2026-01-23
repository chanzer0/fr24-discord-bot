from __future__ import annotations

from datetime import datetime, timezone
import logging

import discord


def _pick_first(data: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


def build_fr24_link(flight: dict, base_url: str) -> str:
    flight_id = _pick_first(flight, ["flight_id", "id", "fr24_id", "uuid"])
    callsign = _pick_first(flight, ["callsign", "flight_number", "flight", "operating_as"])
    if flight_id and callsign:
        return f"{base_url}/{callsign}/{flight_id}"
    if flight_id:
        return f"{base_url}/{flight_id}"
    if callsign:
        return f"{base_url}/{callsign}"
    return base_url


def _format_route(flight: dict) -> str | None:
    origin = _pick_first(
        flight,
        [
            "orig_iata",
            "origin_iata",
            "origin",
            "orig_icao",
            "origin_icao",
        ],
    )
    destination = _pick_first(
        flight,
        [
            "dest_iata",
            "destination_iata",
            "destination",
            "dest_icao",
            "destination_icao",
        ],
    )
    if origin and destination:
        return f"{origin} -> {destination}"
    if destination:
        return destination
    if origin:
        return origin
    return None


def _format_eta(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_embed(
    flight: dict,
    sub_type: str,
    code: str,
    credits_consumed: int | None = None,
    credits_remaining: int | None = None,
) -> discord.Embed:
    title = f"Aircraft match: {code}" if sub_type == "aircraft" else f"Inbound to {code}"
    flight_number = _pick_first(
        flight, ["flight", "flight_number", "flight_number_iata", "flight_number_icao"]
    )
    callsign = _pick_first(flight, ["callsign"])
    embed = discord.Embed(
        title=title,
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )

    if flight_number:
        embed.add_field(name="Flight #", value=flight_number, inline=True)

    registration = _pick_first(flight, ["registration", "reg"])
    if registration:
        embed.add_field(name="Registration", value=registration, inline=True)

    if callsign:
        embed.add_field(name="Callsign", value=callsign, inline=True)

    route = _format_route(flight)
    if route:
        embed.add_field(name="Route", value=route, inline=False)

    eta = _format_eta(_pick_first(flight, ["eta", "estimated_arrival", "eta_utc"]))
    if eta:
        embed.add_field(name="ETA", value=eta, inline=True)

    altitude = _pick_first(flight, ["altitude", "altitude_ft", "alt"])
    speed = _pick_first(flight, ["speed", "ground_speed", "speed_kts"])
    heading = _pick_first(flight, ["heading", "track", "direction"])

    if altitude:
        embed.add_field(name="Altitude", value=str(altitude), inline=True)
    if speed:
        embed.add_field(name="Speed", value=str(speed), inline=True)
    if heading:
        embed.add_field(name="Heading", value=str(heading), inline=True)

    footer_parts = ["Data source: Flightradar24"]
    credit_parts = []
    if credits_consumed is not None:
        credit_parts.append(f"Credits used: {credits_consumed}")
    if credits_remaining is not None:
        credit_parts.append(f"Remaining: {credits_remaining}")
    if credit_parts:
        footer_parts.append(" | ".join(credit_parts))
    embed.set_footer(text=" • ".join(footer_parts))
    return embed


class AlertView(discord.ui.View):
    def __init__(
        self,
        url: str | None,
        db,
        guild_id: str,
        sub_type: str,
        codes: list[str],
        display_code: str,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout_seconds)
        self._log = logging.getLogger(__name__)
        self._db = db
        self._guild_id = guild_id
        self._sub_type = sub_type
        self._codes = self._normalize_codes(codes)
        self._display_code = display_code

        if url:
            self.add_item(discord.ui.Button(label="View on FR24", url=url))

        unsubscribe = discord.ui.Button(
            label="Unsubscribe",
            style=discord.ButtonStyle.danger,
        )
        unsubscribe.callback = self._handle_unsubscribe
        self.add_item(unsubscribe)

    @staticmethod
    def _normalize_codes(codes: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for code in codes:
            if not code:
                continue
            value = str(code).strip().upper()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    async def _handle_unsubscribe(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This button can only be used in a server.",
                ephemeral=True,
            )
            return
        if str(interaction.guild_id) != self._guild_id:
            await interaction.response.send_message(
                "This alert belongs to another server.",
                ephemeral=True,
            )
            return
        removed = 0
        try:
            for code in self._codes:
                if await self._db.remove_subscription(
                    guild_id=self._guild_id,
                    user_id=str(interaction.user.id),
                    sub_type=self._sub_type,
                    code=code,
                ):
                    removed += 1
        except Exception:
            self._log.exception("Failed to remove subscription via alert button")
            await interaction.response.send_message(
                "Failed to unsubscribe. Please try again later.",
                ephemeral=True,
            )
            return
        if removed:
            await interaction.response.send_message(
                f"Unsubscribed from {self._sub_type} {self._display_code}.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"You do not have any subscriptions for {self._display_code}.",
            ephemeral=True,
        )


def build_view(
    url: str | None,
    *,
    db,
    guild_id: str,
    sub_type: str,
    codes: list[str],
    display_code: str,
) -> discord.ui.View | None:
    if not url and not codes:
        return None
    if not db or not guild_id or not sub_type:
        if not url:
            return None
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="View on FR24", url=url))
        return view
    return AlertView(
        url=url,
        db=db,
        guild_id=guild_id,
        sub_type=sub_type,
        codes=codes,
        display_code=display_code,
    )
