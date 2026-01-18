from __future__ import annotations

from datetime import datetime, timezone

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
    origin = _pick_first(flight, ["origin", "origin_icao", "origin_iata"])
    destination = _pick_first(flight, ["destination", "destination_icao", "destination_iata"])
    if origin and destination:
        return f"{origin} -> {destination}"
    if destination:
        return destination
    if origin:
        return origin
    return None


def build_embed(flight: dict, sub_type: str, code: str) -> discord.Embed:
    title = f"Aircraft match: {code}" if sub_type == "aircraft" else f"Inbound to {code}"
    callsign = _pick_first(flight, ["callsign", "flight_number", "flight"])
    description = callsign or "Flight update"

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )

    route = _format_route(flight)
    if route:
        embed.add_field(name="Route", value=route, inline=False)

    aircraft = _pick_first(flight, ["aircraft", "aircraft_type", "aircraft_code", "model"])
    if aircraft:
        embed.add_field(name="Aircraft", value=aircraft, inline=True)

    registration = _pick_first(flight, ["registration", "reg"])
    if registration:
        embed.add_field(name="Registration", value=registration, inline=True)

    altitude = _pick_first(flight, ["altitude", "altitude_ft", "alt"])
    speed = _pick_first(flight, ["speed", "ground_speed", "speed_kts"])
    heading = _pick_first(flight, ["heading", "track", "direction"])

    if altitude:
        embed.add_field(name="Altitude", value=str(altitude), inline=True)
    if speed:
        embed.add_field(name="Speed", value=str(speed), inline=True)
    if heading:
        embed.add_field(name="Heading", value=str(heading), inline=True)

    lat = _pick_first(flight, ["lat", "latitude"])
    lon = _pick_first(flight, ["lon", "lng", "longitude"])
    if lat and lon:
        embed.add_field(name="Position", value=f"{lat}, {lon}", inline=False)

    embed.set_footer(text="Data source: Flightradar24")
    return embed


def build_view(url: str | None) -> discord.ui.View | None:
    if not url:
        return None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="View on FR24", url=url))
    return view
