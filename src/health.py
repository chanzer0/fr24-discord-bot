import importlib.util
import logging


async def run_startup_checks(bot, db, config) -> None:
    log = logging.getLogger(__name__)
    log.info("Startup checks: begin")
    log.info(
        "Config: poll_interval=%s poll_jitter=%s fr24_request_delay=%s fr24_max_requests_per_min=%s fr24_api_key_count=%s fr24_airport_batch_size=%s fr24_aircraft_batch_size=%s retention_days=%s sqlite_path=%s fr24_web_base_url=%s skycards_api_base=%s skycards_client_version=%s log_dir=%s log_retention_hours=%s",
        config.poll_interval_seconds,
        config.poll_jitter_seconds,
        config.fr24_request_delay_seconds,
        config.fr24_max_requests_per_min,
        len(config.fr24_api_keys),
        config.fr24_airport_batch_size,
        config.fr24_aircraft_batch_size,
        config.notification_retention_days,
        config.sqlite_path,
        config.fr24_web_base_url,
        config.skycards_api_base,
        config.skycards_client_version,
        config.log_dir,
        config.log_retention_hours,
    )
    log.info(
        "Secrets loaded: discord_token=%s fr24_api_keys=%s fr24_api_key_count=%s",
        "yes" if config.discord_token else "no",
        "yes" if config.fr24_api_keys else "no",
        len(config.fr24_api_keys),
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
        "Database counts: guild_settings=%s subscriptions=%s notification_log=%s usage_cache=%s fr24_credits=%s bot_settings=%s reference_airports=%s reference_models=%s reference_meta=%s",
        counts["guild_settings"],
        counts["subscriptions"],
        counts["notification_log"],
        counts["usage_cache"],
        counts["fr24_credits"],
        counts["bot_settings"],
        counts["reference_airports"],
        counts["reference_models"],
        counts["reference_meta"],
    )
    if counts["guild_settings"] == 0:
        log.info("No notify channels set yet. Run /set-notify-channel in each guild.")

    for dataset in ("airports", "models"):
        meta = await db.get_reference_meta(dataset)
        if meta:
            log.info(
                "Reference %s: rows=%s updated_at=%s fetched_at=%s",
                dataset,
                meta.get("row_count"),
                meta.get("updated_at"),
                meta.get("fetched_at"),
            )
        else:
            log.info("Reference %s: empty (run /refresh-reference)", dataset)

    polling_enabled = await db.get_setting("polling_enabled")
    poll_interval = await db.get_setting("poll_interval_seconds")
    if polling_enabled is not None or poll_interval is not None:
        log.info(
            "Polling settings: enabled=%s interval_seconds=%s",
            polling_enabled,
            poll_interval,
        )

    log.info("Startup checks: complete")
