from __future__ import annotations

import json

import aiosqlite

from .utils import utc_now_iso


_SCHEMA_SQL = '''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    notify_channel_id TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ("aircraft", "airport")),
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_checked_at TEXT,
    UNIQUE (guild_id, user_id, type, code)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_guild_type_code
    ON subscriptions (guild_id, type, code);

CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL,
    flight_id TEXT NOT NULL,
    notified_at TEXT NOT NULL,
    FOREIGN KEY(subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE,
    UNIQUE (subscription_id, flight_id)
);

CREATE INDEX IF NOT EXISTS idx_notification_log_notified_at
    ON notification_log (notified_at);

CREATE TABLE IF NOT EXISTS usage_cache (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_airports (
    icao TEXT PRIMARY KEY,
    iata TEXT,
    name TEXT NOT NULL,
    city TEXT,
    place_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_reference_airports_iata
    ON reference_airports (iata);

CREATE TABLE IF NOT EXISTS reference_models (
    icao TEXT PRIMARY KEY,
    manufacturer TEXT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_meta (
    dataset TEXT PRIMARY KEY,
    updated_at TEXT,
    fetched_at TEXT NOT NULL,
    row_count INTEGER NOT NULL
);
'''


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA busy_timeout = 5000")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    async def init(self) -> None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.executescript(_SCHEMA_SQL)
        await self._conn.commit()

    async def _changes(self) -> int:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute("SELECT changes()") as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def get_guild_settings(self, guild_id: str) -> dict | None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            "SELECT guild_id, notify_channel_id FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def fetch_guild_channels(self) -> dict[str, str]:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            "SELECT guild_id, notify_channel_id FROM guild_settings"
        ) as cur:
            rows = await cur.fetchall()
        return {row["guild_id"]: row["notify_channel_id"] for row in rows}

    async def set_guild_notify_channel(self, guild_id: str, channel_id: str, updated_by: str) -> None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute(
            '''
            INSERT INTO guild_settings (guild_id, notify_channel_id, updated_by, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET notify_channel_id = excluded.notify_channel_id,
                          updated_by = excluded.updated_by,
                          updated_at = excluded.updated_at
            ''',
            (guild_id, channel_id, updated_by, utc_now_iso()),
        )
        await self._conn.commit()

    async def add_subscription(self, guild_id: str, user_id: str, sub_type: str, code: str) -> bool:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute(
            '''
            INSERT OR IGNORE INTO subscriptions (guild_id, user_id, type, code, created_at)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (guild_id, user_id, sub_type, code, utc_now_iso()),
        )
        await self._conn.commit()
        return await self._changes() == 1

    async def remove_subscription(self, guild_id: str, user_id: str, sub_type: str, code: str) -> bool:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute(
            '''
            DELETE FROM subscriptions
            WHERE guild_id = ? AND user_id = ? AND type = ? AND code = ?
            ''',
            (guild_id, user_id, sub_type, code),
        )
        await self._conn.commit()
        return await self._changes() > 0

    async def fetch_subscriptions(self) -> list[dict]:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            '''
            SELECT id, guild_id, user_id, type, code
            FROM subscriptions
            '''
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def notification_logged(self, subscription_id: int, flight_id: str) -> bool:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            '''
            SELECT 1 FROM notification_log WHERE subscription_id = ? AND flight_id = ?
            ''',
            (subscription_id, flight_id),
        ) as cur:
            row = await cur.fetchone()
        return row is not None

    async def log_notification(self, subscription_id: int, flight_id: str) -> None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute(
            '''
            INSERT OR IGNORE INTO notification_log (subscription_id, flight_id, notified_at)
            VALUES (?, ?, ?)
            ''',
            (subscription_id, flight_id, utc_now_iso()),
        )
        await self._conn.commit()

    async def cleanup_notifications(self, older_than_iso: str) -> int:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute(
            "DELETE FROM notification_log WHERE notified_at < ?",
            (older_than_iso,),
        )
        await self._conn.commit()
        return await self._changes()

    async def get_usage_cache(self) -> dict | None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            "SELECT payload, fetched_at FROM usage_cache WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}
        return {"payload": payload, "fetched_at": row["fetched_at"]}

    async def set_usage_cache(self, payload: dict, fetched_at: str) -> None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        await self._conn.execute(
            '''
            INSERT INTO usage_cache (id, payload, fetched_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET payload = excluded.payload,
                          fetched_at = excluded.fetched_at
            ''',
            (payload_json, fetched_at),
        )
        await self._conn.commit()

    async def get_counts(self) -> dict[str, int]:
        if not self._conn:
            raise RuntimeError("Database not connected")

        async def _count(table: str) -> int:
            async with self._conn.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                row = await cur.fetchone()
            return int(row[0]) if row else 0

        return {
            "guild_settings": await _count("guild_settings"),
            "subscriptions": await _count("subscriptions"),
            "notification_log": await _count("notification_log"),
            "usage_cache": await _count("usage_cache"),
            "reference_airports": await _count("reference_airports"),
            "reference_models": await _count("reference_models"),
            "reference_meta": await _count("reference_meta"),
        }

    async def fetch_user_subscription_codes(
        self, guild_id: str, user_id: str, sub_type: str
    ) -> list[str]:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            '''
            SELECT code FROM subscriptions
            WHERE guild_id = ? AND user_id = ? AND type = ?
            ORDER BY code
            ''',
            (guild_id, user_id, sub_type),
        ) as cur:
            rows = await cur.fetchall()
        return [row["code"] for row in rows]

    async def fetch_reference_airports(self) -> list[dict]:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            '''
            SELECT icao, iata, name, city, place_code
            FROM reference_airports
            ORDER BY icao
            '''
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def fetch_reference_models(self) -> list[dict]:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            '''
            SELECT icao, manufacturer, name
            FROM reference_models
            ORDER BY icao
            '''
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def get_reference_meta(self, dataset: str) -> dict | None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            '''
            SELECT dataset, updated_at, fetched_at, row_count
            FROM reference_meta
            WHERE dataset = ?
            ''',
            (dataset,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def replace_reference_airports(
        self, rows: list[dict], updated_at: str | None, fetched_at: str
    ) -> None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute("BEGIN")
        await self._conn.execute("DELETE FROM reference_airports")
        await self._conn.executemany(
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
        await self._conn.execute(
            '''
            INSERT INTO reference_meta (dataset, updated_at, fetched_at, row_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dataset)
            DO UPDATE SET updated_at = excluded.updated_at,
                          fetched_at = excluded.fetched_at,
                          row_count = excluded.row_count
            ''',
            ("airports", updated_at, fetched_at, len(rows)),
        )
        await self._conn.commit()

    async def replace_reference_models(
        self, rows: list[dict], updated_at: str | None, fetched_at: str
    ) -> None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute("BEGIN")
        await self._conn.execute("DELETE FROM reference_models")
        await self._conn.executemany(
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
        await self._conn.execute(
            '''
            INSERT INTO reference_meta (dataset, updated_at, fetched_at, row_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dataset)
            DO UPDATE SET updated_at = excluded.updated_at,
                          fetched_at = excluded.fetched_at,
                          row_count = excluded.row_count
            ''',
            ("models", updated_at, fetched_at, len(rows)),
        )
        await self._conn.commit()
