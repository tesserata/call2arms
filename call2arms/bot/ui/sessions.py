from typing import Any, Awaitable, Callable, Coroutine

import discord

from bot.ui import campaigns
from call2arms.bot.discord_service import DiscordService
from call2arms.bot.ui._base import (
    ActionButton,
    ConfirmView,
    _BaseLayout,
    _PaginatedLayout,
)
from call2arms.bot.ui._utilities import fmt_ts, parse_datetime, session_line
from call2arms.model import Session
from call2arms.storage import DataStore


class UpcomingSessionsView(_PaginatedLayout):
    def __init__(self, store: DataStore, sessions: list[Session]) -> None:
        self.store = store
        super().__init__(items=sessions)

    def header(self) -> str:
        return f"## Upcoming sessions\n-# Page {self.page + 1}/{self.page_count}"

    def line(self, s: Session) -> str:
        return f"### {session_line(s)}"

    async def on_open(self, interaction: discord.Interaction, s: Session) -> None:
        view = await SessionView.create(
            store=self.store,
            discord_service=interaction.client.discord_service,
            session=s,
            back_factory=lambda: UpcomingSessionsView.create(self.store),
        )
        view.message = interaction.message
        await interaction.response.edit_message(view=view)

    def extra_row(self) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()
        row.add_item(
            ActionButton(
                handler=self._back, label="Back", style=discord.ButtonStyle.secondary
            )
        )
        return row

    async def _back(self, interaction: discord.Interaction) -> None:
        from call2arms.bot.ui.campaigns import CampaignsView

        view = await CampaignsView.create(self.store)
        view.message = interaction.message
        await interaction.response.edit_message(view=view)

    @classmethod
    async def create(cls, store: DataStore, limit: int = 100) -> "UpcomingSessionsView":
        sessions = await store.get_upcoming_sessions(limit=limit)
        return cls(store, sessions)


class SessionView(_BaseLayout):
    def __init__(
        self,
        store: DataStore,
        discord_service: DiscordService,
        session: Session,
        attendees: list[discord.User] | None = None,
        editable: bool = True,
        back_factory: Awaitable[Any] = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.discord_service = discord_service
        self.session = session
        self.attendees = attendees or []
        self.editable = editable
        self.back_factory = back_factory
        self._build()

    @classmethod
    async def create(
        cls,
        store: DataStore,
        discord_service: DiscordService,
        session: Session,
        editable: bool = True,
        back_factory: Awaitable[Any] = None,
    ) -> "SessionView":
        return cls(
            store,
            discord_service,
            session,
            await cls._fetch_attendees(discord_service, session),
            editable,
            back_factory,
        )

    @staticmethod
    async def _fetch_attendees(
        discord_service: DiscordService, session: Session
    ) -> list[discord.User]:
        if not session.announced:
            return []
        return (
            await discord_service.get_reaction_users(
                session.announcement_channel_id, session.announcement_message_id, "🐐"
            )
            or []
        )

    async def refresh(self) -> None:
        self.session = await self.store.get_session(
            self.session.campaign_id, self.session.id
        )
        self.attendees = await self._fetch_attendees(self.discord_service, self.session)
        self._build()

    def _text(self) -> str:
        lines = [
            f"## {self.session.campaign_name} session #{self.session.number}",
            f"**Starts:** {fmt_ts(self.session.starts_at, 'F')}",
            f"**Status:** {self.session.status}",
        ]
        if self.session.announced or self.session.completed:
            names = (
                "\n".join(f"• {u.display_name}" for u in self.attendees) or "No one yet"
            )
            lines.append(f"**Attendance ({len(self.attendees)}):**\n{names}")
        return "\n".join(lines)

    def _build(self) -> None:
        self.clear_items()
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(self._text()))

        if self.editable:
            row1 = discord.ui.ActionRow()
            if not self.session.completed:
                row1.add_item(
                    ActionButton(
                        handler=self._change_time,
                        label="Change time",
                        style=discord.ButtonStyle.primary,
                    )
                )
            row1.add_item(
                ActionButton(
                    handler=self._back,
                    label="Back",
                    style=discord.ButtonStyle.secondary,
                )
            )
            container.add_item(row1)

            row2 = discord.ui.ActionRow()
            if not self.session.completed:
                row2.add_item(
                    ActionButton(
                        handler=self._cancel,
                        label="Cancel session",
                        style=discord.ButtonStyle.danger,
                        disabled=self.session.cancelled,
                    )
                )
            row2.add_item(
                ActionButton(
                    handler=self._delete,
                    label="Delete",
                    style=discord.ButtonStyle.danger,
                )
            )
            container.add_item(row2)

        self.add_item(container)

    async def _change_time(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            ChangeTimeModal(self.store, self.session, self)
        )

    async def _cancel(self, interaction: discord.Interaction) -> None:
        await self.store.cancel_session(self.session.campaign_id, self.session.id)
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def _delete(self, interaction: discord.Interaction) -> None:
        confirm = ConfirmView(f"Delete this session?\n{session_line(self.session)}")
        await interaction.response.edit_message(view=confirm)
        confirm.message = await interaction.original_response()
        await confirm.wait()
        if confirm.confirmed:
            await self.store.delete_session(self.session.campaign_id, self.session.id)
            view = await self._get_back_view()
            view.message = confirm.message
            await interaction.edit_original_response(view=view)
        else:
            await interaction.edit_original_response(view=self)

    async def _back(self, interaction: discord.Interaction) -> None:
        view = await self._get_back_view()
        view.message = interaction.message
        await interaction.response.edit_message(view=view)

    async def _get_back_view(self) -> discord.ui.View:
        if self.back_factory:
            view = await self.back_factory()
        else:
            view = await UpcomingSessionsView.create(self.store)
        return view


class ChangeTimeModal(discord.ui.Modal, title="Change session time"):
    new_time: discord.ui.TextInput = discord.ui.TextInput(
        label="New start time",
        placeholder="e.g. 2026-09-20 15:00  (parsed as UTC)",
        required=True,
        max_length=100,
    )

    def __init__(
        self, store: DataStore, session: Session, edit_view: SessionView
    ) -> None:
        super().__init__()
        self.store = store
        self.session = session
        self.edit_view = edit_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            new_dt = parse_datetime(self.new_time.value)
        except (ValueError, OverflowError):
            await interaction.response.send_message(
                f"Couldn't parse `{self.new_time.value}` as a date/time.",
                ephemeral=True,
            )
            return
        await self.store.move_session(self.session.campaign_id, self.session.id, new_dt)
        await self.edit_view.refresh()
        await interaction.response.edit_message(view=self.edit_view)
