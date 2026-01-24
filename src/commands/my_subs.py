import math

import discord
from discord import app_commands

from ..reference_data import format_airport_label, format_model_label


class SubscriptionsView(discord.ui.View):
    def __init__(self, db, guild_id: str, user_id: int, subs: list[dict]) -> None:
        super().__init__(timeout=300)
        self.db = db
        self.guild_id = guild_id
        self.user_id = user_id
        self.subs = subs
        self.page_size = 10
        self.page = 0
        self._rebuild()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This list belongs to another user.", ephemeral=True
            )
            return False
        return True

    def _page_count(self) -> int:
        if not self.subs:
            return 1
        return max(1, math.ceil(len(self.subs) / self.page_size))

    def _page_items(self) -> list[dict]:
        start = self.page * self.page_size
        end = start + self.page_size
        return self.subs[start:end]

    def _build_embed(self) -> discord.Embed:
        total = len(self.subs)
        title = f"Your subscriptions ({total})"
        lines = ["Select a subscription below to remove it."]
        offset = self.page * self.page_size
        for idx, item in enumerate(self._page_items(), start=offset + 1):
            lines.append(f"{idx}. {item['type']}: {item['label']}")
        description = "\n".join(lines) if lines else "No subscriptions yet."
        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        pages = self._page_count()
        if pages > 1:
            embed.set_footer(text=f"Page {self.page + 1}/{pages}")
        return embed

    def _rebuild(self) -> None:
        self.clear_items()
        if not self.subs:
            return

        pages = self._page_count()

        prev_button = discord.ui.Button(
            label="Prev",
            style=discord.ButtonStyle.secondary,
            disabled=self.page <= 0,
        )
        next_button = discord.ui.Button(
            label="Next",
            style=discord.ButtonStyle.secondary,
            disabled=self.page >= (pages - 1),
        )

        async def prev_callback(interaction: discord.Interaction) -> None:
            self.page = max(0, self.page - 1)
            self._rebuild()
            await interaction.response.edit_message(
                embed=self._build_embed(), view=self
            )

        async def next_callback(interaction: discord.Interaction) -> None:
            self.page = min(pages - 1, self.page + 1)
            self._rebuild()
            await interaction.response.edit_message(
                embed=self._build_embed(), view=self
            )

        prev_button.callback = prev_callback
        next_button.callback = next_callback
        self.add_item(prev_button)
        self.add_item(next_button)

        options = []
        for item in self._page_items():
            label = item["label"]
            value = f"{item['type']}|{item['code']}"
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=item["type"],
                )
            )

        select = discord.ui.Select(
            placeholder="Remove a subscription",
            min_values=1,
            max_values=1,
            options=options,
        )

        async def select_callback(interaction: discord.Interaction) -> None:
            selection = select.values[0]
            sub_type, code = selection.split("|", 1)
            removed = await self.db.remove_subscription(
                guild_id=self.guild_id,
                user_id=str(self.user_id),
                sub_type=sub_type,
                code=code,
            )
            if removed:
                self.subs = [
                    item
                    for item in self.subs
                    if not (item["type"] == sub_type and item["code"] == code)
                ]
                if self.page >= self._page_count():
                    self.page = max(0, self._page_count() - 1)
            if not self.subs:
                await interaction.response.edit_message(
                    content="No subscriptions yet.",
                    embed=None,
                    view=None,
                )
                return
            self._rebuild()
            await interaction.response.edit_message(
                embed=self._build_embed(), view=self
            )

        select.callback = select_callback
        self.add_item(select)


def _build_label(item: dict, ref) -> str:
    if item["type"] == "aircraft" and ref:
        return format_model_label(ref)
    if item["type"] == "airport" and ref:
        return format_airport_label(ref)
    return item["code"]


def register(tree, db, config, reference_data) -> None:
    @tree.command(name="my-subs", description="List your current subscriptions.")
    async def my_subs(interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        rows = await db.fetch_user_subscriptions(
            guild_id=str(interaction.guild_id),
            user_id=str(interaction.user.id),
        )
        if not rows:
            await interaction.response.send_message(
                "You do not have any subscriptions yet.",
                ephemeral=True,
            )
            return

        subs = []
        for row in rows:
            code = row["code"]
            sub_type = row["type"]
            if sub_type == "aircraft":
                ref = await reference_data.get_model(code)
            elif sub_type == "airport":
                if len(code) == 3:
                    ref = await reference_data.get_airport_by_iata(code)
                else:
                    ref = await reference_data.get_airport(code)
            else:
                ref = None
            label = _build_label(row, ref)
            subs.append(
                {
                    "type": sub_type,
                    "code": code,
                    "label": label,
                }
            )

        view = SubscriptionsView(
            db=db,
            guild_id=str(interaction.guild_id),
            user_id=interaction.user.id,
            subs=subs,
        )
        await interaction.response.send_message(
            embed=view._build_embed(),
            view=view,
            ephemeral=True,
        )
