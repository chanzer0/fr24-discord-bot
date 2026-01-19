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


@dataclass(frozen=True)
class Config:
    discord_token: str
    fr24_api_key: str
    bot_owner_id: int
    poll_interval_seconds: int
    poll_jitter_seconds: int
    fr24_request_delay_seconds: float
    notification_retention_days: int
    sqlite_path: str
    fr24_web_base_url: str
    log_level: str


def load_config() -> Config:
    return Config(
        discord_token=_require_env("DISCORD_TOKEN"),
        fr24_api_key=_require_env("FR24_API_KEY"),
        bot_owner_id=int(_require_env("BOT_OWNER_ID")),
        poll_interval_seconds=_int_env("POLL_INTERVAL_SECONDS", 60),
        poll_jitter_seconds=_int_env("POLL_JITTER_SECONDS", 5),
        fr24_request_delay_seconds=_float_env("FR24_REQUEST_DELAY_SECONDS", 0.2),
        notification_retention_days=_int_env("NOTIFICATION_RETENTION_DAYS", 7),
        sqlite_path=os.getenv("SQLITE_PATH", "/data/bot.db"),
        fr24_web_base_url=os.getenv("FR24_WEB_BASE_URL", "https://www.flightradar24.com"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
