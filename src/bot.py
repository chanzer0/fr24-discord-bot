import logging

import discord
from discord import app_commands
from dotenv import load_dotenv

from .commands import setup_commands
from .config import load_config
from .db import Database
from .fr24.client import Fr24Client
from .health import run_startup_checks
from .poller import cleanup_loop, poll_loop
from .poller_state import PollerState
from .reference_data import ReferenceDataService


class FlightBot(discord.Client):
    def __init__(self, config, db, fr24, reference_data) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.config = config
        self.db = db
        self.fr24 = fr24
        self.reference_data = reference_data
        self.poller_state: PollerState | None = None

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.init()
        await self.reference_data.load_from_db()
        poll_interval = self.config.poll_interval_seconds
        stored_interval = await self.db.get_setting("poll_interval_seconds")
        if stored_interval:
            try:
                poll_interval = int(stored_interval)
            except ValueError:
                logging.getLogger(__name__).warning(
                    "Invalid poll_interval_seconds setting: %s", stored_interval
                )
        stored_enabled = await self.db.get_setting("polling_enabled")
        polling_enabled = True
        if stored_enabled is not None:
            polling_enabled = stored_enabled.strip().lower() in ("1", "true", "yes", "on")
        self.poller_state = PollerState(polling_enabled, poll_interval)
        setup_commands(
            self.tree,
            self.db,
            self.config,
            self.fr24,
            self.reference_data,
            self.poller_state,
        )
        await run_startup_checks(self, self.db, self.config)
        self.loop.create_task(poll_loop(self, self.db, self.fr24, self.config, self.poller_state))
        self.loop.create_task(cleanup_loop(self.db, self.config))
        await self.tree.sync()

    async def on_ready(self) -> None:
        log = logging.getLogger(__name__)
        if self.user:
            log.info("Connected to Discord as %s (%s)", self.user, self.user.id)
        log.info("Guilds connected: %s", len(self.guilds))

    async def close(self) -> None:
        await super().close()
        await self.db.close()


def main() -> None:
    load_dotenv()
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )

    db = Database(config.sqlite_path)
    fr24 = Fr24Client(config.fr24_api_key, config.fr24_max_requests_per_min)
    reference_data = ReferenceDataService(
        db,
        config.skycards_api_base,
        config.skycards_client_version,
    )
    bot = FlightBot(config, db, fr24, reference_data)
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()
