# Commands

## `/set-notify-channel`
Owner-only command to set the guild-wide default channel for notifications.

Example:
- `/set-notify-channel #flight-alerts`

## `/set-change-roles`
Owner-only command to set roles that are mentioned when Skycards reference data changes.

Examples:
- `/set-change-roles aircraft_role:@AircraftChanges airport_role:@AirportChanges`
- `/set-change-roles aircraft_role:@AircraftChanges`

## `/set-type-cards-role`
Owner-only command to set the role mentioned for missing type card alerts.

Example:
- `/set-type-cards-role role:@TypeCards`

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
Show the latest cached FR24 credits remaining values per key (updated after each FR24 API call),
including parked status and retry time when applicable.

## `/park-key`
Owner-only command to park an FR24 API key for 24 hours.

Notes:
- Autocomplete shows the key index and the masked suffix (e.g., `1: ***ABCD`).
- Parking via this command does not send a guild alert.

## `/unpark-key`
Owner-only command to unpark a previously parked FR24 API key.

Notes:
- Autocomplete shows the key index and the masked suffix (e.g., `1: ***ABCD`).

## `/info`
Show reference data for an airport or aircraft. The response includes a JSON attachment
with the full record plus a small inline preview.

Examples:
- `/info airport RAE`
- `/info aircraft A388`

Note:
- Run `/refresh-reference` to load the latest reference data if records are missing.

## `/filterlist`
Generate a comma-separated list of aircraft ICAO codes for FR24 filters.

Examples:
- `/filterlist field="Rarity Tier" op="=" value="uncommon"` (A380/A388)
- `/filterlist field="Rarity" op=">=" value="3.00"` (rareness/100)
- `/filterlist field="Weight" op=">=" value="200"` (tons)
- `/filterlist field="Wingspan" op="between" value="60..80"` (meters)
- `/filterlist field="Num Engines" op="in" value="2,4"`
- `/filterlist field="Manufacturers" op="contains" value="AIRBUS"`
- `/filterlist field="Military" op="is" value="true"`

Notes:
- Text comparisons are case-insensitive.
- Fields supported: Manufacturers, Rarity Tier, Rarity (rareness/100), Num Observed, Num Engines,
  Wingspan (m), Seats, Speed (knots), First Flight (year), Weight (tons), Military (true/false).
- Manufacturer autocomplete only shows values with 2+ aircraft, but manual entry accepts any value.
- FR24 supports up to 99 ICAO codes per filter; results are split into 99-per-line chunks when needed.
- If model details are missing, run `/refresh-reference` first.
- Long lists are truncated in the message with a full `filterlist.txt` attachment.

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
