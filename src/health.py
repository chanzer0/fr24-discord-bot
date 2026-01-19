import importlib.util
import logging


async def run_startup_checks(bot, db, config) -> None:
    log = logging.getLogger(__name__)
    log.info("Startup checks: begin")
    log.info(
        "Config: poll_interval=%s poll_jitter=%s fr24_request_delay=%s retention_days=%s sqlite_path=%s fr24_web_base_url=%s",
        config.poll_interval_seconds,
        config.poll_jitter_seconds,
        config.fr24_request_delay_seconds,
        config.notification_retention_days,
        config.sqlite_path,
        config.fr24_web_base_url,
    )
    log.info(
        "Secrets loaded: discord_token=%s fr24_api_key=%s",
        "yes" if config.discord_token else "no",
        "yes" if config.fr24_api_key else "no",
    )

    if getattr(bot.intents, "message_content", False):
        log.info("Discord intents: message_content enabled")
    else:
        log.info("Discord intents: message_content disabled (expected for slash commands)")

    nacl_available = importlib.util.find_spec("nacl") is not None
    if nacl_available:
        log.info("PyNaCl installed: voice features available")
    else:
        log.info("PyNaCl not installed: voice features disabled")

    counts = await db.get_counts()
    log.info(
        "Database counts: guild_settings=%s subscriptions=%s notification_log=%s",
        counts["guild_settings"],
        counts["subscriptions"],
        counts["notification_log"],
    )
    if counts["guild_settings"] == 0:
        log.info("No notify channels set yet. Run /set-notify-channel in each guild.")

    log.info("Startup checks: complete")
