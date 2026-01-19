from dataclasses import dataclass
import os


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required env var: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _parse_owner_ids() -> list[int]:
    raw = os.getenv("BOT_OWNER_IDS")
    if raw:
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        if not parts:
            raise ValueError("BOT_OWNER_IDS must contain at least one ID")
        owner_ids: list[int] = []
        seen: set[int] = set()
        for item in parts:
            try:
                value = int(item)
            except ValueError as exc:
                raise ValueError("BOT_OWNER_IDS must be a CSV of integers") from exc
            if value in seen:
                continue
            seen.add(value)
            owner_ids.append(value)
        if not owner_ids:
            raise ValueError("BOT_OWNER_IDS must contain at least one ID")
        return owner_ids
    legacy = os.getenv("BOT_OWNER_ID")
    if legacy:
        try:
            return [int(legacy.strip())]
        except ValueError as exc:
            raise ValueError("BOT_OWNER_ID must be an integer") from exc
    raise ValueError("Missing required env var: BOT_OWNER_IDS")


@dataclass(frozen=True)
class Config:
    discord_token: str
    fr24_api_key: str
    bot_owner_ids: list[int]
    poll_interval_seconds: int
    poll_jitter_seconds: int
    fr24_request_delay_seconds: float
    fr24_max_requests_per_min: int
    fr24_airport_batch_size: int
    notification_retention_days: int
    sqlite_path: str
    fr24_web_base_url: str
    skycards_api_base: str
    skycards_client_version: str
    log_level: str


def load_config() -> Config:
    return Config(
        discord_token=_require_env("DISCORD_TOKEN"),
        fr24_api_key=_require_env("FR24_API_KEY"),
        bot_owner_ids=_parse_owner_ids(),
        poll_interval_seconds=_int_env("POLL_INTERVAL_SECONDS", 300),
        poll_jitter_seconds=_int_env("POLL_JITTER_SECONDS", 5),
        fr24_request_delay_seconds=_float_env("FR24_REQUEST_DELAY_SECONDS", 0.2),
        fr24_max_requests_per_min=max(1, _int_env("FR24_MAX_REQUESTS_PER_MIN", 10)),
        fr24_airport_batch_size=min(15, max(1, _int_env("FR24_AIRPORT_BATCH_SIZE", 5))),
        notification_retention_days=_int_env("NOTIFICATION_RETENTION_DAYS", 7),
        sqlite_path=os.getenv("SQLITE_PATH", "/data/bot.db"),
        fr24_web_base_url=os.getenv("FR24_WEB_BASE_URL", "https://www.flightradar24.com"),
        skycards_api_base=os.getenv("SKYCARDS_API_BASE", "https://api.skycards.oldapes.com"),
        skycards_client_version=os.getenv("SKYCARDS_CLIENT_VERSION", "2.0.18"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
