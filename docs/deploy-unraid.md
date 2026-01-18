# Unraid Deployment

## Build and publish image
The GitHub Actions workflow publishes to GHCR on every push to main.

Image:
- ghcr.io/<owner>/<repo>:main

## Unraid container setup
1. Create a new container from the GHCR image.
2. Map a persistent volume to /data (e.g., /mnt/user/appdata/fr24-discord-bot:/data).
3. Set environment variables (see .env.example).
4. Set restart policy to "unless-stopped".

## Updates
- Triggered by GitHub Actions on main.
- Pull latest image in Unraid or use Watchtower to auto-update.
