from __future__ import annotations

import asyncio
import io
import json
import logging
from datetime import datetime, timezone

import discord


_REFRESH_INTERVAL_SECONDS = 30 * 60
_MAX_MESSAGE_LENGTH = 2000


def _normalize_icao(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip().upper()
    return cleaned or None


def _format_value(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _format_fields(row: dict) -> str:
    parts = []
    for key in sorted(row.keys()):
        parts.append(f"{key}={_format_value(row.get(key))}")
    return ", ".join(parts)


def _format_changes(changes: list[tuple[str, object, object]]) -> str:
    parts = []
    for field, old_value, new_value in changes:
        parts.append(
            f"{field}: {_format_value(old_value)} -> {_format_value(new_value)}"
        )
    return "; ".join(parts)


def _model_icao(row: dict) -> str | None:
    return _normalize_icao(row.get("icao") or row.get("id"))


def _airport_icao(row: dict) -> str | None:
    return _normalize_icao(row.get("icao"))


def _model_name(row: dict, fallback: str) -> str:
    manufacturer = str(row.get("manufacturer") or "").strip()
    name = str(row.get("name") or "").strip()
    if manufacturer and name:
        return f"{manufacturer} {name}"
    return manufacturer or name or fallback


def _airport_name(row: dict, fallback: str) -> str:
    name = str(row.get("name") or "").strip()
    city = str(row.get("city") or "").strip()
    place_code = str(row.get("placeCode") or row.get("place_code") or "").strip()
    if not name:
        return fallback
    suffix_parts = [part for part in (city, place_code) if part]
    if suffix_parts:
        return f"{name} ({', '.join(suffix_parts)})"
    return name


def _diff_rows(old_rows: list[dict], new_rows: list[dict], kind: str) -> dict:
    if kind not in ("models", "airports"):
        raise ValueError("kind must be models or airports")
    old_map: dict[str, dict] = {}
    new_map: dict[str, dict] = {}

    extractor = _model_icao if kind == "models" else _airport_icao
    for row in old_rows:
        if not isinstance(row, dict):
            continue
        icao = extractor(row)
        if not icao:
            continue
        old_map[icao] = row
    for row in new_rows:
        if not isinstance(row, dict):
            continue
        icao = extractor(row)
        if not icao:
            continue
        new_map[icao] = row

    added = []
    removed = []
    updated = []

    added_keys = sorted(set(new_map.keys()) - set(old_map.keys()))
    removed_keys = sorted(set(old_map.keys()) - set(new_map.keys()))
    shared_keys = sorted(set(old_map.keys()) & set(new_map.keys()))

    for icao in added_keys:
        row = new_map[icao]
        name = _model_name(row, icao) if kind == "models" else _airport_name(row, icao)
        added.append({"icao": icao, "name": name, "row": row})

    for icao in removed_keys:
        row = old_map[icao]
        name = _model_name(row, icao) if kind == "models" else _airport_name(row, icao)
        removed.append({"icao": icao, "name": name, "row": row})

    for icao in shared_keys:
        old_row = old_map[icao]
        new_row = new_map[icao]
        keys = sorted(set(old_row.keys()) | set(new_row.keys()))
        changes: list[tuple[str, object, object]] = []
        for key in keys:
            old_value = old_row.get(key)
            new_value = new_row.get(key)
            if old_value == new_value:
                continue
            changes.append((key, old_value, new_value))
        if changes:
            name = (
                _model_name(new_row, icao)
                if kind == "models"
                else _airport_name(new_row, icao)
            )
            updated.append(
                {
                    "icao": icao,
                    "name": name,
                    "row": new_row,
                    "changes": changes,
                }
            )

    return {
        "added": added,
        "removed": removed,
        "updated": updated,
        "has_changes": bool(added or removed or updated),
    }


def _format_section(
    label: str,
    entries: list[dict],
    kind: str,
) -> list[str]:
    lines = [f"{label} ({len(entries)})"]
    if not entries:
        lines.append("- (none)")
        return lines
    if label == "NEW":
        for entry in entries:
            row = entry.get("row") or {}
            lines.append(f"- {entry['icao']} - {entry['name']}")
            for key in sorted(row.keys()):
                lines.append(f"  - {key}={_format_value(row.get(key))}")
        return lines
    if label == "UPDATED":
        for entry in entries:
            changes = entry.get("changes") or []
            lines.append(f"- {entry['icao']} - {entry['name']}")
            for field, old_value, new_value in changes:
                lines.append(
                    f"  - {field}: {_format_value(old_value)} -> {_format_value(new_value)}"
                )
        return lines
    for entry in entries:
        lines.append(f"- {entry['icao']} - {entry['name']}")
    return lines


def _format_timestamp(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _build_changelog_text(results: dict[str, dict]) -> str:
    fetched_at = None
    for dataset in ("models", "airports"):
        entry = results.get(dataset)
        if entry and entry.get("fetched_at"):
            fetched_at = entry["fetched_at"]
            break
    header_time = _format_timestamp(fetched_at)
    lines = [f"Skycards reference update ({header_time})", ""]
    for dataset in ("models", "airports"):
        entry = results.get(dataset)
        if not entry or not entry.get("diff") or not entry["diff"]["has_changes"]:
            continue
        label = "Models" if dataset == "models" else "Airports"
        diff = entry["diff"]
        lines.append(f"{label}:")
        lines.extend(_format_section("NEW", diff["added"], dataset))
        lines.extend(_format_section("UPDATED", diff["updated"], dataset))
        lines.extend(_format_section("REMOVED", diff["removed"], dataset))
        lines.append("")
    return "\n".join(lines).rstrip()


async def _send_changelog(
    bot,
    channel_id: str,
    content: str | None,
    file_content: str | None,
) -> None:
    log = logging.getLogger(__name__)
    try:
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(channel_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to resolve channel %s: %s", channel_id, exc)
        return

    allowed_mentions = discord.AllowedMentions(roles=True, users=False, everyone=False)
    try:
        if file_content is not None:
            data = file_content.encode("utf-8")
            file = discord.File(
                fp=io.BytesIO(data),
                filename="skycards-changelog.txt",
            )
            await channel.send(content="", file=file, allowed_mentions=allowed_mentions)
        else:
            await channel.send(content=content or "", allowed_mentions=allowed_mentions)
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("Failed to send reference changelog to %s: %s", channel_id, exc)


async def _refresh_and_notify(bot, db, reference_data) -> None:
    log = logging.getLogger(__name__)
    results = await reference_data.refresh_with_payloads("all")
    if not results:
        return
    for dataset in ("models", "airports"):
        entry = results.get(dataset)
        if not entry:
            continue
        entry["diff"] = _diff_rows(
            entry.get("old_rows", []),
            entry.get("new_rows", []),
            dataset,
        )

    models_changed = bool(results.get("models", {}).get("diff", {}).get("has_changes"))
    airports_changed = bool(
        results.get("airports", {}).get("diff", {}).get("has_changes")
    )
    if not models_changed and not airports_changed:
        log.info("Reference refresh complete (no changes)")
        return

    changelog_text = _build_changelog_text(results)
    if not changelog_text:
        return

    targets = await db.fetch_guild_notification_targets()
    if not targets:
        return

    for target in targets:
        channel_id = target.get("notify_channel_id")
        if not channel_id:
            continue
        mentions: list[str] = []
        if models_changed and target.get("aircraft_change_role_id"):
            mentions.append(f"<@&{target['aircraft_change_role_id']}>")
        if airports_changed and target.get("airport_change_role_id"):
            mentions.append(f"<@&{target['airport_change_role_id']}>")
        content = changelog_text
        if mentions:
            content = f"{' '.join(mentions)}\n{changelog_text}"
        if len(content) > _MAX_MESSAGE_LENGTH:
            await _send_changelog(bot, channel_id, None, changelog_text)
        else:
            await _send_changelog(bot, channel_id, content, None)


async def reference_refresh_loop(bot, db, _config, reference_data) -> None:
    log = logging.getLogger(__name__)
    log.info(
        "Reference refresh loop started (interval=%ss)", _REFRESH_INTERVAL_SECONDS
    )
    while True:
        try:
            await _refresh_and_notify(bot, db, reference_data)
        except Exception:
            log.exception("Reference refresh loop failed")
        await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
