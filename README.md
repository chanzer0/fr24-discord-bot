# fr24-discord-bot

Discord bot that lets users subscribe to Flightradar24 aircraft-type, registration, or inbound airport alerts. The bot polls FR24 on an interval and posts rich notifications in a guild-wide default channel.

## Features
- Subscribe/unsubscribe to aircraft ICAO type codes (e.g., A388, C172)
- Subscribe/unsubscribe to registration/tail numbers (e.g., N123AB)
- Subscribe/unsubscribe to inbound airport codes (IATA preferred, e.g., WAW or EPWA)
- Owner-only default notification channel per guild via `/set-notify-channel`
- Skycards-powered autocomplete for airports/models with owner refresh
- `/info` command returns full airport/aircraft reference records
- `/filterlist` command generates comma-separated ICAO lists for FR24 filters
- Background polling with dedupe and backoff-friendly pacing
- Per-guild notifications tag all subscribers for the same ICAO in a single message (mentions truncated if needed)
- SQLite persistence with daily cleanup of stale notification logs
- Docker-friendly for Unraid deployments

## Commands
- `/set-notify-channel <channel>` (owner-only)
- `/subscribe <aircraft|registration|airport> <code>`
- `/unsubscribe <aircraft|registration|airport> <code>`
- `/my-subs`
- `/refresh-reference <airports|models|all>` (owner-only)
- `/credits-remaining`
- `/info <aircraft|airport> <code>`
- `/filterlist <field> <op> <value>`
- `/logs` (owner-only)
- `/start` (owner-only)
- `/stop` (owner-only)
- `/set-polling-interval <seconds>` (owner-only)
- `/help`

## Quickstart (local)
Requires Python 3.11+ (matches the Docker image).

1. `python -m venv .venv`
2. Activate the venv
   - Windows: `.\.venv\Scripts\activate`
   - Linux/macOS: `source .venv/bin/activate`
3. Copy `.env.example` to `.env` and fill values
4. `pip install -r requirements.txt`
5. `python -m src.bot`

## Environment variables
- `DISCORD_TOKEN`
- `FR24_API_KEYS` (CSV of FR24 API keys)
- `BOT_OWNER_IDS` (CSV of Discord user IDs)
- `POLL_INTERVAL_SECONDS` (default 150)
- `POLL_JITTER_SECONDS` (default 5)
- `FR24_REQUEST_DELAY_SECONDS` (default 0.5; only used when 1 key is configured, otherwise forced to 0)
- `FR24_MAX_REQUESTS_PER_MIN` (default 10, per key)
- `FR24_AIRPORT_BATCH_SIZE` (default 15, max 15)
- `FR24_AIRCRAFT_BATCH_SIZE` (default 15, max 15)
- `FR24_REGISTRATION_BATCH_SIZE` (default 15, max 15)
- `NOTIFICATION_RETENTION_DAYS` (default 7)
- `SQLITE_PATH` (default `/data/bot.db`)
- `FR24_WEB_BASE_URL` (default `https://www.flightradar24.com`)
- `SKYCARDS_API_BASE` (default `https://api.skycards.oldapes.com`)
- `SKYCARDS_CLIENT_VERSION` (default 2.0.18)
- `LOG_DIR` (default `/data/logs`)
- `LOG_RETENTION_HOURS` (default 24)
- `LOG_LEVEL` (default `INFO`)

## Docker (local)
- `docker compose up --build`

## Unraid deployment
- Build and push image via GitHub Actions to GHCR.
- Use the included Unraid template (`unraid-template.xml`) or create a container manually.
- Map `/data` to a persistent host path.
- Configure environment variables (see `.env.example`).
- See `docs/deploy-unraid.md` for details.

## Data retention
- The bot stores subscription metadata and a notification dedupe log only.
- Notification logs are pruned daily based on NOTIFICATION_RETENTION_DAYS.
- Airport/model reference data is cached in SQLite for autocomplete.
- Guild, channel, and user display names are stored alongside IDs for easier admin visibility.

## Credits visibility
- Each FR24-powered notification includes the credits consumed/remaining plus the masked FR24 key suffix used.
- The latest credits remaining values per key are stored in SQLite and available via `/credits-remaining`.

## Logs and startup checks
- On startup, the bot logs configuration (non-sensitive), DB counts, and intent/voice status.
- PyNaCl warnings only affect voice features, which are not used by this bot.
- Poller errors are posted to each guild notify channel and tag the bot owner.
- Logs are written to LOG_DIR with hourly rotation and 24-hour retention by default.
- Owners can view recent logs with `/logs` or `python -m src.admin logs`.

## Docs
- `docs/architecture.md`
- `docs/commands.md`
- `docs/deploy-unraid.md`
- `docs/rate-limits.md`
- `docs/ops.md`
- `unraid-template.xml`
