import math
from typing import Any, Awaitable, Callable

import discord
from loguru import logger

VIEW_TIMEOUT = 60 * 10
PAGE_SIZE = 5

Handler = Callable[[discord.Interaction], Awaitable[None]]


class ActionButton(discord.ui.Button):
    def __init__(self, handler: Handler, **kwargs) -> None:
        super().__init__(**kwargs)
        self._handler = handler

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._handler(interaction)


class _BaseLayout(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            logger.debug("Could not disable view on timeout")

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: Any) -> None:
        logger.exception(error)


class _PaginatedLayout(_BaseLayout):
    page_size: int = PAGE_SIZE

    def __init__(self, items: list) -> None:
        super().__init__()
        self.items = items
        self.page = 0
        self._build()

    def header(self) -> str:
        raise NotImplementedError

    def line(self, item) -> str:
        raise NotImplementedError

    async def on_open(self, interaction: discord.Interaction, item) -> None:
        raise NotImplementedError

    def extra_row(self) -> discord.ui.ActionRow | None:
        return None

    @property
    def page_count(self) -> int:
        return max(1, math.ceil(len(self.items) / self.page_size))

    def _current_slice(self) -> list:
        return self.items[self.page * self.page_size : (self.page + 1) * self.page_size]

    def _build(self) -> None:
        self.clear_items()
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(self.header()))

        page = self._current_slice()
        if not page:
            container.add_item(discord.ui.TextDisplay("*Nothing here yet.*"))
        for item in page:
            container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay(self.line(item)),
                    accessory=ActionButton(
                        handler=self._make_open(item),
                        label="View",
                        style=discord.ButtonStyle.secondary,
                    ),
                )
            )

        if self.page_count > 1:
            container.add_item(discord.ui.Separator())
            container.add_item(self._pager())

        extra = self.extra_row()
        if extra is not None:
            container.add_item(extra)

        self.add_item(container)

    def _make_open(self, item) -> Handler:
        async def _open(interaction: discord.Interaction) -> None:
            await self.on_open(interaction, item)

        return _open

    def _pager(self) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()
        row.add_item(
            ActionButton(
                handler=self._page_prev,
                label="◀",
                style=discord.ButtonStyle.secondary,
                disabled=self.page <= 0,
            )
        )
        row.add_item(
            ActionButton(
                handler=self._page_next,
                label="▶",
                style=discord.ButtonStyle.secondary,
                disabled=self.page >= self.page_count - 1,
            )
        )
        return row

    async def _page_prev(self, interaction: discord.Interaction) -> None:
        if self.page > 0:
            self.page -= 1
            self._build()
        await interaction.response.edit_message(view=self)

    async def _page_next(self, interaction: discord.Interaction) -> None:
        if self.page < self.page_count - 1:
            self.page += 1
            self._build()
        await interaction.response.edit_message(view=self)


class ConfirmView(_BaseLayout):

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.confirmed = False
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(prompt))
        row = discord.ui.ActionRow()
        row.add_item(
            ActionButton(
                handler=self._confirm, label="Confirm", style=discord.ButtonStyle.danger
            )
        )
        row.add_item(
            ActionButton(
                handler=self._cancel,
                label="Cancel",
                style=discord.ButtonStyle.secondary,
            )
        )
        container.add_item(row)
        self.add_item(container)

    async def _confirm(self, interaction: discord.Interaction) -> None:
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    async def _cancel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        self.stop()
