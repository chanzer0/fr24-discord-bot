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
from .usage import usage_loop


class FlightBot(discord.Client):
    def __init__(self, config, db, fr24) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.config = config
        self.db = db
        self.fr24 = fr24

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.init()
        setup_commands(self.tree, self.db, self.config, self.fr24)
        await run_startup_checks(self, self.db, self.config)
        self.loop.create_task(poll_loop(self, self.db, self.fr24, self.config))
        self.loop.create_task(cleanup_loop(self.db, self.config))
        self.loop.create_task(usage_loop(self, self.db, self.fr24, self.config))
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
    fr24 = Fr24Client(config.fr24_api_key)
    bot = FlightBot(config, db, fr24)
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()
