# Architecture

## Components
- Discord bot (discord.py): slash commands, validation, and notifications.
- FR24 client (fr24sdk): fetches live flight positions.
- Poller: background task that groups subscriptions and queries FR24 once per unique code.
- Reference data service: fetches airport/model data from Skycards and caches it for autocomplete.
- SQLite storage: persists guild settings, subscriptions, and notification dedupe logs.

## Data flow
1. Bot owner runs `/set-notify-channel` to store the default channel for a guild.
2. Users subscribe to aircraft, registration, or inbound airport codes.
3. Poller reads all subscriptions, groups by code, and calls FR24.
4. For each matching flight, the bot sends an embed to the guild's notify channel and tags the user.
5. A dedupe log prevents repeated notifications for the same flight.
6. The owner can run `/refresh-reference` to update airport/model data used for autocomplete.

## Storage
- SQLite file at `SQLITE_PATH` (default `/data/bot.db`).
- Tables:
  - guild_settings: one row per guild with notify channel ID, plus guild/channel names.
  - subscriptions: one row per user per (type, code), including user/guild display names.
  - notification_log: dedupe log to avoid repeat alerts.
  - fr24_credits: latest credits remaining/consumed from FR24 response headers.
  - bot_settings: global bot settings like polling interval and enabled state.
  - reference_airports: ICAO/IATA and airport details used for autocomplete and /info.
  - reference_models: ICAO and aircraft model details used for autocomplete and /info.
  - reference_meta: metadata for the reference datasets.
- WAL mode and busy timeout are enabled for stability on Unraid.

## Resource safeguards
- Configurable polling interval and small request delay between FR24 calls.
- Batch FR24 calls by (type, code) to avoid duplicate requests.
- Daily cleanup of notification logs to cap database growth.
- Reference datasets are stored in SQLite and cached in memory for fast autocomplete.
- No full flight history is stored; only dedupe entries are retained.

## Observability
- Startup checks log non-sensitive config, DB counts, and capability status.
- Poller logs cycle completion and cleanup logs pruned rows.
- Logs are written to rotating files in `LOG_DIR` for quick review.
