# Commands

## /set-notify-channel
Owner-only command to set the guild-wide default channel for notifications.

Example:
- /set-notify-channel #flight-alerts

## /subscribe
Subscribe to aircraft type or inbound airport alerts.

Examples:
- /subscribe aircraft A388
- /subscribe airport WAW

Notes:
- Autocomplete suggests ICAO codes from the Skycards reference datasets.
- Manual ICAO input is allowed; the bot warns if it is not found in the reference data.

## /unsubscribe
Remove an existing subscription.

Examples:
- /unsubscribe aircraft A388
- /unsubscribe airport WAW

Notes:
- Autocomplete only shows your own saved subscriptions.

## /my-subs
Show your current subscriptions and remove them from an ephemeral list.

## /refresh-reference
Owner-only command to refresh airport/model reference data used for autocomplete.

Example:
- /refresh-reference all

Notes:
- Run once after first deploy to seed autocomplete results.

## /credits-remaining
Show the latest cached FR24 credits remaining value (updated after each FR24 API call).

## /start
Owner-only command to start the FR24 polling loop.

## /stop
Owner-only command to stop the FR24 polling loop after the current cycle.

## /set-polling-interval
Owner-only command to change the polling interval (in seconds).

## /help
Show usage and tips.
