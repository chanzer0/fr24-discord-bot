# Rate Limits and Backoff

## Discord
- discord.py automatically respects Discord rate limits.
- The bot avoids high-frequency writes by batching notifications per poll cycle.

## Flightradar24
- The bot uses fr24sdk and respects poll pacing and per-request delays.
- Configure POLL_INTERVAL_SECONDS and FR24_REQUEST_DELAY_SECONDS to stay within your plan limits.
- Verify your plan's documented rate limits and adjust values accordingly.
