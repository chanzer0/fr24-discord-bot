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


def cmd_status(conn: sqlite3.Connection) -> None:
    tables = ("guild_settings", "subscriptions", "notification_log", "usage_cache")
    counts = {}
    for table in tables:
        cur = conn.execute(f"SELECT COUNT(*) AS count FROM {table}")
        counts[table] = int(cur.fetchone()["count"])
    print("Database:", conn.execute("PRAGMA database_list").fetchone()["file"])
    print("Counts:", ", ".join(f"{k}={v}" for k, v in counts.items()))

    cur = conn.execute(
        "SELECT guild_id, notify_channel_id, updated_at FROM guild_settings ORDER BY guild_id"
    )
    rows = cur.fetchall()
    if rows:
        print("Notify channels:")
        _print_rows(rows, ["guild_id", "notify_channel_id", "updated_at"])


def cmd_guilds(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        "SELECT guild_id, notify_channel_id, updated_by, updated_at FROM guild_settings ORDER BY guild_id"
    )
    rows = cur.fetchall()
    _print_rows(rows, ["guild_id", "notify_channel_id", "updated_by", "updated_at"])


def cmd_subs(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (
        "SELECT id, guild_id, user_id, type, code, created_at FROM subscriptions WHERE 1=1"
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
    _print_rows(rows, ["id", "guild_id", "user_id", "type", "code", "created_at"])


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
    query = "SELECT id, guild_id, user_id, type, code, created_at FROM subscriptions ORDER BY created_at DESC"
    rows = conn.execute(query).fetchall()
    writer = csv.writer(os.sys.stdout)
    writer.writerow(["id", "guild_id", "user_id", "type", "code", "created_at"])
    for row in rows:
        writer.writerow([row["id"], row["guild_id"], row["user_id"], row["type"], row["code"], row["created_at"]])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FR24 Discord bot admin CLI")
    parser.add_argument("--db", default=_default_db_path(), help="Path to SQLite DB")

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
    finally:
        conn.close()


if __name__ == "__main__":
    main()
