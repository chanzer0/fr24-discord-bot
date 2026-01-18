# Architecture

## Components
- Discord bot (discord.py): slash commands, validation, and notifications.
- FR24 client (fr24sdk): fetches live flight positions.
- Poller: background task that groups subscriptions and queries FR24.
- SQLite storage: persists guild settings, subscriptions, and notification dedupe logs.

## Data flow
1. Bot owner runs /set-notify-channel to store the default channel for a guild.
2. Users subscribe to aircraft or inbound airport codes.
3. Poller reads all subscriptions, groups by code, and calls FR24.
4. For each matching flight, the bot sends an embed to the guild's notify channel and tags the user.
5. A dedupe log prevents repeated notifications for the same flight.

## Resource safeguards
- Configurable polling interval and small request delay between FR24 calls.
- SQLite WAL mode and busy timeout for stability.
- Daily cleanup of notification logs.
