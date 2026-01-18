import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from .commands import setup_commands
from .config import load_config
from .db import Database
from .fr24.client import Fr24Client
from .poller import cleanup_loop, poll_loop


class FlightBot(commands.Bot):
    def __init__(self, config, db, fr24) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.db = db
        self.fr24 = fr24

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.init()
        setup_commands(self.tree, self.db, self.config)
        self.loop.create_task(poll_loop(self, self.db, self.fr24, self.config))
        self.loop.create_task(cleanup_loop(self.db, self.config))
        await self.tree.sync()

    async def close(self) -> None:
        await super().close()
        await self.db.close()


def main() -> None:
    load_dotenv()
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db = Database(config.sqlite_path)
    fr24 = Fr24Client(config.fr24_api_key)
    bot = FlightBot(config, db, fr24)
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()
