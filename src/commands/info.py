import io
import json

import discord
from discord import app_commands

from ..reference_data import format_airport_label, format_model_label
from ..validation import normalize_code


def _resolve_info_type(interaction: discord.Interaction) -> str | None:
    namespace = getattr(interaction, "namespace", None)
    value = getattr(namespace, "info_type", None)
    if isinstance(value, app_commands.Choice):
        return value.value
    if isinstance(value, str):
        return value
    return None


def _format_code_block(payload: dict) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if len(text) > 1800:
        text = text[:1800] + "\n..."
    return f"```\n{text}\n```"


def _airport_label_from_record(record: dict, fallback: str) -> str:
    iata = record.get("iata") or record.get("IATA")
    icao = record.get("icao") or record.get("ICAO") or fallback
    name = record.get("name")
    city = record.get("city")
    place_code = record.get("placeCode") or record.get("place_code")
    details = ", ".join(part for part in (name, city, place_code) if part)
    code = iata or icao or fallback
    return f"{code} - {details}" if details else code


def _model_label_from_record(record: dict, fallback: str) -> str:
    icao = record.get("id") or record.get("icao") or record.get("ICAO") or fallback
    manufacturer = record.get("manufacturer")
    name = record.get("name")
    details = " ".join(part for part in (manufacturer, name) if part)
    return f"{icao} - {details}" if details else str(icao)


def register(tree, db, config, reference_data) -> None:
    async def code_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        info_type = _resolve_info_type(interaction)
        if info_type == "aircraft":
            models = await reference_data.search_models(current)
            return [
                app_commands.Choice(name=format_model_label(model), value=model.icao)
                for model in models
            ]
        if info_type == "airport":
            airports = await reference_data.search_airports(current)
            return [
                app_commands.Choice(
                    name=format_airport_label(airport),
                    value=airport.iata or airport.icao,
                )
                for airport in airports
            ]
        return []

    @tree.command(name="info", description="Show details for an airport or aircraft.")
    @app_commands.describe(info_type="Info type", code="ICAO/IATA code")
    @app_commands.choices(
        info_type=[
            app_commands.Choice(name="aircraft", value="aircraft"),
            app_commands.Choice(name="airport", value="airport"),
        ]
    )
    @app_commands.autocomplete(code=code_autocomplete)
    async def info(
        interaction: discord.Interaction,
        info_type: app_commands.Choice[str],
        code: str,
    ) -> None:
        normalized = normalize_code(info_type.value, code)
        if not normalized:
            await interaction.response.send_message(
                "Invalid code format. Codes must be at least 2 characters.",
                ephemeral=True,
            )
            return

        if info_type.value == "airport":
            record = await db.get_reference_airport_record(normalized)
            if not record:
                await interaction.response.send_message(
                    f"No airport record found for {normalized}. Try /refresh-reference.",
                    ephemeral=True,
                )
                return
            label = _airport_label_from_record(record, normalized)
            embed = discord.Embed(
                title=f"Airport info: {label}",
                color=discord.Color.blue(),
            )
        else:
            record = await db.get_reference_model_record(normalized)
            if not record:
                await interaction.response.send_message(
                    f"No aircraft record found for {normalized}. Try /refresh-reference.",
                    ephemeral=True,
                )
                return
            label = _model_label_from_record(record, normalized)
            embed = discord.Embed(
                title=f"Aircraft info: {label}",
                color=discord.Color.green(),
            )

        payload = record if isinstance(record, dict) else {}
        preview = _format_code_block(payload)
        file_bytes = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
        file = discord.File(io.BytesIO(file_bytes), filename=f"{info_type.value}-{normalized}.json")
        await interaction.response.send_message(
            embed=embed,
            content=preview,
            file=file,
            ephemeral=True,
        )
