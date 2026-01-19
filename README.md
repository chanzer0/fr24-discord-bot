# fr24-discord-bot

Discord bot that lets users subscribe to Flightradar24 aircraft-type or inbound airport alerts. The bot polls FR24 on an interval and posts rich notifications in a guild-wide default channel.

## Features
- Subscribe/unsubscribe to aircraft ICAO type codes (e.g., A388, C172)
- Subscribe/unsubscribe to inbound airport ICAO codes (e.g., WAW)
- Owner-only default notification channel per guild via /set-notify-channel
- Background polling with dedupe and backoff-friendly pacing
- SQLite persistence with daily cleanup of stale notification logs
- Docker-friendly for Unraid deployments

## Commands
- /set-notify-channel <channel> (owner-only)
- /subscribe <aircraft|airport> <code>
- /unsubscribe <aircraft|airport> <code>
- /help

## Quickstart (local)
Requires Python 3.11+ (matches the Docker image).

1. python -m venv .venv
2. Activate the venv
   - Windows: .\.venv\Scripts\activate
   - Linux/macOS: source .venv/bin/activate
3. Copy .env.example to .env and fill values
4. pip install -r requirements.txt
5. python -m src.bot

## Environment variables
- DISCORD_TOKEN
- FR24_API_KEY
- BOT_OWNER_ID (your Discord user ID)
- POLL_INTERVAL_SECONDS (default 60)
- POLL_JITTER_SECONDS (default 5)
- FR24_REQUEST_DELAY_SECONDS (default 0.2)
- NOTIFICATION_RETENTION_DAYS (default 7)
- SQLITE_PATH (default /data/bot.db)
- FR24_WEB_BASE_URL (default https://www.flightradar24.com)
- LOG_LEVEL (default INFO)

## Docker (local)
- docker compose up --build

## Unraid deployment
- Build and push image via GitHub Actions to GHCR.
- Use the included Unraid template (unraid-template.xml) or create a container manually.
- Map /data to a persistent host path.
- Configure environment variables (see .env.example).
See docs/deploy-unraid.md for details.

## Data retention
- The bot stores subscription metadata and a notification dedupe log only.
- Notification logs are pruned daily based on NOTIFICATION_RETENTION_DAYS.

## Logs and startup checks
- On startup, the bot logs configuration (non-sensitive), DB counts, and intent/voice status.
- PyNaCl warnings only affect voice features, which are not used by this bot.

## Docs
- docs/architecture.md
- docs/commands.md
- docs/deploy-unraid.md
- docs/rate-limits.md
- docs/ops.md
- unraid-template.xml
