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

## /usage
Show cached FR24 API usage statistics. If the cache is older than 5 minutes, the bot refreshes it before responding.

Example:
- /usage

## /refresh-reference
Owner-only command to refresh airport/model reference data used for autocomplete.

Example:
- /refresh-reference all

Notes:
- Run once after first deploy to seed autocomplete results.

## /help
Show usage and tips.
