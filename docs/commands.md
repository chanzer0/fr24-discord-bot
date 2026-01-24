# Commands

## `/set-notify-channel`
Owner-only command to set the guild-wide default channel for notifications.

Example:
- `/set-notify-channel #flight-alerts`

## `/subscribe`
Subscribe to aircraft type, registration, or inbound airport alerts.

Examples:
- `/subscribe aircraft A388`
- `/subscribe registration N123AB`
- `/subscribe airport WAW`

Notes:
- Autocomplete matches airport IATA/ICAO codes from the Skycards reference datasets (IATA preferred).
- Manual airport or aircraft code input is allowed; the bot warns if it is not found in the reference data.
- Registration codes are manual entry only (no autocomplete).
- Notifications for the same code in a guild are combined into one message tagging all subscribers (mentions truncated if needed).

## `/unsubscribe`
Remove an existing subscription.

Examples:
- `/unsubscribe aircraft A388`
- `/unsubscribe registration N123AB`
- `/unsubscribe airport WAW`

Notes:
- Autocomplete only shows your own saved subscriptions.

## `/my-subs`
Show your current subscriptions and remove them from an ephemeral list.

## `/refresh-reference`
Owner-only command to refresh airport/model reference data used for autocomplete.

Example:
- `/refresh-reference all`

Notes:
- Run once after first deploy to seed autocomplete results.

## `/credits-remaining`
Show the latest cached FR24 credits remaining values per key (updated after each FR24 API call).

## `/info`
Show reference data for an airport or aircraft. The response includes a JSON attachment
with the full record plus a small inline preview.

Examples:
- `/info airport RAE`
- `/info aircraft A388`

Note:
- Run `/refresh-reference` to load the latest reference data if records are missing.

## `/logs`
Owner-only command to view recent log lines.

Example:
- `/logs 50`
- `/logs 100 contains:rate limit`

## `/start`
Owner-only command to start the FR24 polling loop.

## `/stop`
Owner-only command to stop the FR24 polling loop after the current cycle.

## `/set-polling-interval`
Owner-only command to change the polling interval (in seconds).

## `/help`
Show usage and tips.
