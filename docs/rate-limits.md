# Rate Limits and Backoff

## Discord
- `discord.py` automatically handles bucket and global rate limits.
- The bot sends notifications in the poll loop instead of per-request bursts.
- If Discord returns a `429`, `discord.py` waits and retries automatically.

## Flightradar24
- The bot uses `fr24sdk` and enforces a per-key max requests per minute.
- When `FR24_API_KEYS` includes multiple keys, requests rotate across keys and each key enforces its own rate limit.
- Subscriptions are grouped by (type, code) so each target is queried once per cycle.
- Configure `FR24_MAX_REQUESTS_PER_MIN` per key for your plan (default 10/min).
- `POLL_INTERVAL_SECONDS`, `FR24_REQUEST_DELAY_SECONDS`, `FR24_AIRPORT_BATCH_SIZE`, `FR24_AIRCRAFT_BATCH_SIZE`, and `FR24_REGISTRATION_BATCH_SIZE` further pace cycles.
- If FR24 responses indicate throttling, increase `FR24_MAX_REQUESTS_PER_MIN` only if your plan allows it.
- Always verify current plan limits in the FR24 API documentation.
- Each FR24 response includes credit headers; notifications display consumed/remaining credits plus the masked key suffix.

## Pacing controls
- `POLL_INTERVAL_SECONDS`: base poll cadence (default 150s).
- `POLL_JITTER_SECONDS`: adds jitter to avoid synchronized spikes.
- `FR24_REQUEST_DELAY_SECONDS`: base delay between FR24 requests within a cycle. When multiple API keys are configured, this is forced to `0` and pacing is handled by the client pool limiter.
- `FR24_MAX_REQUESTS_PER_MIN`: per-key cap across FR24 requests.
- `FR24_AIRPORT_BATCH_SIZE`: number of airport codes per request (max 15).
- `FR24_AIRCRAFT_BATCH_SIZE`: number of aircraft codes per request (max 15).
- `FR24_REGISTRATION_BATCH_SIZE`: number of registration codes per request (max 15).
