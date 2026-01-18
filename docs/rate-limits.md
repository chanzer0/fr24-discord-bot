# Rate Limits and Backoff

## Discord
- discord.py automatically handles bucket and global rate limits.
- The bot sends notifications in the poll loop instead of per-request bursts.
- If Discord returns a 429, discord.py waits and retries automatically.

## Flightradar24
- The bot uses fr24sdk and requests are paced by configuration.
- Subscriptions are grouped by (type, code) so each target is queried once per cycle.
- Configure POLL_INTERVAL_SECONDS and FR24_REQUEST_DELAY_SECONDS to match your plan limits.
- If FR24 responses indicate throttling, increase the poll interval and request delay.
- Always verify current plan limits in the FR24 API documentation.

## Pacing controls
- POLL_INTERVAL_SECONDS: base poll cadence.
- POLL_JITTER_SECONDS: adds jitter to avoid synchronized spikes.
- FR24_REQUEST_DELAY_SECONDS: delay between FR24 requests within a cycle.
