# Ops and Admin CLI

This repository includes a lightweight admin CLI that you can run inside the container terminal to inspect the SQLite database and log output.
Logs are written to `LOG_DIR` (default `/data/logs`) with hourly rotation and 24-hour retention by default.
Poller errors are posted to each guild notify channel tagging the bot owner.

## How to run
Open the Unraid container terminal and run:

```bash
python -m src.admin <command> [options]
```

You can point it at a custom database file if needed:

```bash
python -m src.admin --db /data/bot.db <command>
```

## Commands
### status
Shows DB counts and configured notify channels.

```bash
python -m src.admin status
```

### guilds
Lists guild notify channel settings.

```bash
python -m src.admin guilds
```

### subs
Lists subscriptions with optional filters.

```bash
python -m src.admin subs
python -m src.admin subs --guild 123 --type aircraft
python -m src.admin subs --user 456 --code A388
```

### subs-by-user (quick SQL)
Shows subscription counts grouped by user (user name + ID).

```bash
python - <<'PY'
import os
import sqlite3

db_path = os.getenv("SQLITE_PATH", "/data/bot.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT user_name,
           user_id,
           COUNT(*) AS subs
    FROM subscriptions
    GROUP BY user_id, user_name
    ORDER BY subs DESC, user_name
    """
).fetchall()
print("user_name\tuser_id\tsubs")
for row in rows:
    print(f"{row['user_name']}\t{row['user_id']}\t{row['subs']}")
conn.close()
PY
```

### recent
Shows recent notification logs.

```bash
python -m src.admin recent
python -m src.admin recent --limit 50
python -m src.admin recent --subscription 10
```

### clear-notifications
Deletes notification log entries older than N days.

```bash
python -m src.admin clear-notifications --older-than-days 7
```

### logs
Tail recent log output from the rotated log files.

```bash
python -m src.admin logs
python -m src.admin logs --tail 100
python -m src.admin logs --contains rate limit
```

### remove-subs
Delete subscriptions by ID (with confirmation).

```bash
python -m src.admin remove-subs 12 15 18
```

Skip the prompt:

```bash
python -m src.admin remove-subs 12 15 --yes
```

### export-subs
Exports subscriptions as CSV to stdout.

```bash
python -m src.admin export-subs > /data/subscriptions.csv
```

CSV columns include guild/user names alongside IDs for easier review.

### reference-status
Shows reference dataset metadata (row counts and timestamps).

```bash
python -m src.admin reference-status
```

### refresh-reference
Fetches airports/models from the Skycards API and stores them in SQLite.

```bash
python -m src.admin refresh-reference --dataset all
python -m src.admin refresh-reference --dataset airports
```
