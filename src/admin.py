import argparse
import csv
import os
import sqlite3
from datetime import datetime, timedelta, timezone


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _default_db_path() -> str:
    return os.getenv("SQLITE_PATH", "/data/bot.db")


def _print_rows(rows: list[sqlite3.Row], columns: list[str]) -> None:
    if not rows:
        print("No results.")
        return
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(str(row[col])))
    header = "  ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("-" * len(header))
    for row in rows:
        print("  ".join(str(row[col]).ljust(widths[col]) for col in columns))


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row["name"] for row in rows}
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    conn.commit()


def _ensure_core_columns(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "guild_settings", "guild_name", "TEXT")
    _ensure_column(conn, "guild_settings", "notify_channel_name", "TEXT")
    _ensure_column(conn, "guild_settings", "updated_by_name", "TEXT")
    _ensure_column(conn, "subscriptions", "guild_name", "TEXT")
    _ensure_column(conn, "subscriptions", "user_name", "TEXT")


def _ensure_reference_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS reference_airports (
            icao TEXT PRIMARY KEY,
            iata TEXT,
            name TEXT NOT NULL,
            city TEXT,
            place_code TEXT
        )
        '''
    )
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS reference_models (
            icao TEXT PRIMARY KEY,
            manufacturer TEXT,
            name TEXT NOT NULL
        )
        '''
    )
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS reference_meta (
            dataset TEXT PRIMARY KEY,
            updated_at TEXT,
            fetched_at TEXT NOT NULL,
            row_count INTEGER NOT NULL
        )
        '''
    )
    conn.commit()


def cmd_status(conn: sqlite3.Connection) -> None:
    _ensure_core_columns(conn)
    _ensure_reference_tables(conn)
    tables = (
        "guild_settings",
        "subscriptions",
        "notification_log",
        "usage_cache",
        "reference_airports",
        "reference_models",
        "reference_meta",
    )
    counts = {}
    for table in tables:
        cur = conn.execute(f"SELECT COUNT(*) AS count FROM {table}")
        counts[table] = int(cur.fetchone()["count"])
    print("Database:", conn.execute("PRAGMA database_list").fetchone()["file"])
    print("Counts:", ", ".join(f"{k}={v}" for k, v in counts.items()))

    cur = conn.execute(
        '''
        SELECT guild_id, guild_name, notify_channel_id, notify_channel_name, updated_at
        FROM guild_settings
        ORDER BY guild_id
        '''
    )
    rows = cur.fetchall()
    if rows:
        print("Notify channels:")
        _print_rows(
            rows,
            ["guild_id", "guild_name", "notify_channel_id", "notify_channel_name", "updated_at"],
        )


def cmd_reference_status(conn: sqlite3.Connection) -> None:
    _ensure_reference_tables(conn)
    cur = conn.execute(
        "SELECT dataset, updated_at, fetched_at, row_count FROM reference_meta ORDER BY dataset"
    )
    rows = cur.fetchall()
    if rows:
        print("Reference datasets:")
        _print_rows(rows, ["dataset", "row_count", "updated_at", "fetched_at"])
    else:
        print("No reference metadata found.")


def cmd_refresh_reference(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    from .reference_data import (
        fetch_reference_payload_sync,
        parse_airports_payload,
        parse_models_payload,
    )

    _ensure_reference_tables(conn)

    datasets = (args.dataset,) if args.dataset != "all" else ("airports", "models")
    for dataset in datasets:
        endpoint = "airports" if dataset == "airports" else "models"
        payload = fetch_reference_payload_sync(
            args.skycards_api_base, endpoint, args.skycards_client_version
        )
        fetched_at = datetime.now(timezone.utc).isoformat()
        if dataset == "airports":
            updated_at, rows = parse_airports_payload(payload)
            conn.execute("DELETE FROM reference_airports")
            conn.executemany(
                '''
                INSERT INTO reference_airports (icao, iata, name, city, place_code)
                VALUES (?, ?, ?, ?, ?)
                ''',
                [
                    (
                        row.get("icao"),
                        row.get("iata"),
                        row.get("name"),
                        row.get("city"),
                        row.get("place_code"),
                    )
                    for row in rows
                ],
            )
            row_count = len(rows)
        else:
            updated_at, rows = parse_models_payload(payload)
            conn.execute("DELETE FROM reference_models")
            conn.executemany(
                '''
                INSERT INTO reference_models (icao, manufacturer, name)
                VALUES (?, ?, ?)
                ''',
                [
                    (
                        row.get("icao"),
                        row.get("manufacturer"),
                        row.get("name"),
                    )
                    for row in rows
                ],
            )
            row_count = len(rows)
        conn.execute(
            '''
            INSERT INTO reference_meta (dataset, updated_at, fetched_at, row_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dataset)
            DO UPDATE SET updated_at = excluded.updated_at,
                          fetched_at = excluded.fetched_at,
                          row_count = excluded.row_count
            ''',
            (dataset, updated_at, fetched_at, row_count),
        )
        conn.commit()
        print(
            f"Refreshed {dataset}: {row_count} rows (updated_at={updated_at}, fetched_at={fetched_at})"
        )


def cmd_guilds(conn: sqlite3.Connection) -> None:
    _ensure_core_columns(conn)
    cur = conn.execute(
        '''
        SELECT guild_id, guild_name, notify_channel_id, notify_channel_name,
               updated_by, updated_by_name, updated_at
        FROM guild_settings
        ORDER BY guild_id
        '''
    )
    rows = cur.fetchall()
    _print_rows(
        rows,
        [
            "guild_id",
            "guild_name",
            "notify_channel_id",
            "notify_channel_name",
            "updated_by",
            "updated_by_name",
            "updated_at",
        ],
    )


def cmd_subs(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    _ensure_core_columns(conn)
    query = (
        '''
        SELECT id, guild_id, guild_name, user_id, user_name, type, code, created_at
        FROM subscriptions
        WHERE 1=1
        '''
    )
    params = []
    if args.guild:
        query += " AND guild_id = ?"
        params.append(args.guild)
    if args.user:
        query += " AND user_id = ?"
        params.append(args.user)
    if args.type:
        query += " AND type = ?"
        params.append(args.type)
    if args.code:
        query += " AND code = ?"
        params.append(args.code.upper())
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    _print_rows(
        rows,
        [
            "id",
            "guild_id",
            "guild_name",
            "user_id",
            "user_name",
            "type",
            "code",
            "created_at",
        ],
    )


def cmd_recent(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (
        "SELECT id, subscription_id, flight_id, notified_at FROM notification_log WHERE 1=1"
    )
    params = []
    if args.subscription:
        query += " AND subscription_id = ?"
        params.append(args.subscription)
    query += " ORDER BY notified_at DESC LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(query, params).fetchall()
    _print_rows(rows, ["id", "subscription_id", "flight_id", "notified_at"])


def cmd_clear_notifications(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than_days)
    cur = conn.execute(
        "DELETE FROM notification_log WHERE notified_at < ?",
        (cutoff.isoformat(),),
    )
    conn.commit()
    print(f"Deleted {cur.rowcount} notification_log rows older than {args.older_than_days} days.")


def cmd_export_subs(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    _ensure_core_columns(conn)
    query = '''
        SELECT id, guild_id, guild_name, user_id, user_name, type, code, created_at
        FROM subscriptions
        ORDER BY created_at DESC
    '''
    rows = conn.execute(query).fetchall()
    writer = csv.writer(os.sys.stdout)
    writer.writerow(
        ["id", "guild_id", "guild_name", "user_id", "user_name", "type", "code", "created_at"]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["guild_id"],
                row["guild_name"],
                row["user_id"],
                row["user_name"],
                row["type"],
                row["code"],
                row["created_at"],
            ]
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FR24 Discord bot admin CLI")
    parser.add_argument("--db", default=_default_db_path(), help="Path to SQLite DB")
    parser.add_argument(
        "--skycards-api-base",
        default=os.getenv("SKYCARDS_API_BASE", "https://api.skycards.oldapes.com"),
        help="Skycards API base URL",
    )
    parser.add_argument(
        "--skycards-client-version",
        default=os.getenv("SKYCARDS_CLIENT_VERSION", "2.0.18"),
        help="Skycards client version header",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show counts and notify channels")
    sub.add_parser("guilds", help="List guild notify channels")

    subs = sub.add_parser("subs", help="List subscriptions")
    subs.add_argument("--guild")
    subs.add_argument("--user")
    subs.add_argument("--type", choices=["aircraft", "airport"])
    subs.add_argument("--code")

    recent = sub.add_parser("recent", help="Show recent notifications")
    recent.add_argument("--limit", type=int, default=20)
    recent.add_argument("--subscription", type=int)

    clear = sub.add_parser("clear-notifications", help="Delete old notification logs")
    clear.add_argument("--older-than-days", type=int, default=7)

    sub.add_parser("export-subs", help="Export subscriptions as CSV")
    sub.add_parser("reference-status", help="Show reference dataset status")

    refresh = sub.add_parser("refresh-reference", help="Refresh reference datasets")
    refresh.add_argument(
        "--dataset", choices=["airports", "models", "all"], default="all"
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    conn = _connect(args.db)
    try:
        if args.command == "status":
            cmd_status(conn)
        elif args.command == "guilds":
            cmd_guilds(conn)
        elif args.command == "subs":
            cmd_subs(conn, args)
        elif args.command == "recent":
            cmd_recent(conn, args)
        elif args.command == "clear-notifications":
            cmd_clear_notifications(conn, args)
        elif args.command == "export-subs":
            cmd_export_subs(conn, args)
        elif args.command == "reference-status":
            cmd_reference_status(conn)
        elif args.command == "refresh-reference":
            cmd_refresh_reference(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
