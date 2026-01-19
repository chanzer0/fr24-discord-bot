# Unraid Deployment

## Build and publish image (GHCR)
1. Push to the main branch. The GitHub Actions workflow publishes to GHCR.
2. Confirm the workflow succeeded in GitHub Actions.
3. Set the package visibility:
   - Public: no auth needed to pull.
   - Private: requires a GitHub PAT with read:packages when pulling.
4. If private, add ghcr.io credentials in Unraid (Docker settings -> Registry Login).

Image:
- ghcr.io/chanzer0/fr24-discord-bot:main

## Unraid template setup (recommended)
Before adding the repo as a template source, verify unraid-template.xml points at your GitHub owner/repo.

1. Add the template repository URL in Unraid:
   - Docker tab -> Docker Repositories -> Template repositories.
   - Add https://github.com/chanzer0/fr24-discord-bot
2. Click Add Container and pick the fr24-discord-bot template.
3. Map /data to a persistent host path:
   - /mnt/user/appdata/fr24-discord-bot:/data
4. Fill in required environment variables (see below).
5. Set restart policy to "unless-stopped" and create the container.

## Manual container setup (alternative)
1. Create a new container from the GHCR image.
2. Map /data to a persistent host path (e.g., /mnt/user/appdata/fr24-discord-bot:/data).
3. Set environment variables (see .env.example).
4. Set restart policy to "unless-stopped".

## Required environment variables
- DISCORD_TOKEN
- FR24_API_KEY
- BOT_OWNER_IDS

## Optional environment variables
- POLL_INTERVAL_SECONDS
- POLL_JITTER_SECONDS
- FR24_REQUEST_DELAY_SECONDS
- FR24_MAX_REQUESTS_PER_MIN
- NOTIFICATION_RETENTION_DAYS
- SQLITE_PATH
- FR24_WEB_BASE_URL
- SKYCARDS_API_BASE
- SKYCARDS_CLIENT_VERSION
- LOG_LEVEL

## Initial bot setup
1. Invite the bot with applications.commands and bot scopes.
2. Run /set-notify-channel as the bot owner.
3. Run /refresh-reference all to populate autocomplete data.
4. Test /subscribe aircraft A388 or /subscribe airport WAW.

## Container terminal tips
- You can open a terminal for the container in Unraid and run:
  - python -m src.admin status
  - python -m src.admin subs
  - python -m src.admin recent
See docs/ops.md for the full admin CLI.

## Updates
- Triggered by GitHub Actions on main.
- Pull latest image in Unraid or use Watchtower to auto-update.
