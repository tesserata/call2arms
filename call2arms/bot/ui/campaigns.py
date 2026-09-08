from datetime import UTC, datetime

import discord
from dateutil.rrule import rrulestr
from loguru import logger
from rrule_humanize import humanize

from call2arms.bot.ui._base import (
    ActionButton,
    ConfirmView,
    _BaseLayout,
    _PaginatedLayout,
)
from call2arms.bot.ui._utilities import parse_datetime, session_line
from call2arms.bot.ui.sessions import SessionView
from call2arms.model import Campaign, Session
from call2arms.storage import DataStore
from call2arms.config import get_config

CONFIG = get_config()
HISTORY_LIMIT = 10


class CampaignsView(_PaginatedLayout):
    def __init__(self, store: DataStore, campaigns: list[Campaign]) -> None:
        self.store = store
        super().__init__(items=campaigns)

    def header(self) -> str:
        return "## Campaigns"

    def line(self, c: Campaign) -> str:
        finished = " *(finished)*" if not c.active else ""
        return f"### {c.name}{finished}\n-# {c.past_sessions_count} sessions played"

    async def on_open(self, interaction: discord.Interaction, c: Campaign) -> None:
        view = CampaignActionsView(self.store, c)
        view.message = interaction.message
        await interaction.response.edit_message(view=view)

    def extra_row(self) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()
        row.add_item(
            ActionButton(
                handler=self._create,
                label="Create campaign",
                style=discord.ButtonStyle.success,
            )
        )
        return row

    async def _create(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddCampaignModal(self.store))

    @classmethod
    async def create(cls, store: DataStore) -> "CampaignsView":
        return cls(store, await store.list_campaigns())


class CampaignActionsView(_BaseLayout):
    def __init__(self, store: DataStore, campaign: Campaign) -> None:
        super().__init__()
        self.store = store
        self.campaign = campaign
        self._build()

    def _text(self) -> str:
        lines = [f"## {self.campaign.name}"]
        if not self.campaign.active:
            lines.append("-# (finished)")
        if self.campaign.rrule:
            schedule_text = humanize(self.campaign.rrule)
        else:
            schedule_text = "No recurrence"
        lines.append(f"**Schedule:** {schedule_text}")
        lines.append(f"**Past sessions:** {self.campaign.past_sessions_count}")
        lines.append(f"**Scheduled sessions:** {self.campaign.upcoming_sessions_count}")
        return "\n".join(lines)

    def _build(self) -> None:
        self.clear_items()
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(self._text()))

        row1 = discord.ui.ActionRow()
        row1.add_item(
            ActionButton(
                handler=self._history,
                label="History",
                style=discord.ButtonStyle.primary,
            )
        )
        if self.campaign.active:
            row1.add_item(
                ActionButton(
                    handler=self._upcoming,
                    label="Upcoming",
                    style=discord.ButtonStyle.primary,
                )
            )
        container.add_item(row1)

        row2 = discord.ui.ActionRow()
        if self.campaign.active:
            row2.add_item(
                ActionButton(
                    handler=self._add_session,
                    label="Add session",
                    style=discord.ButtonStyle.success,
                )
            )
        row2.add_item(
            ActionButton(
                handler=self._edit_rrule,
                label="Edit recurrence rule",
                style=discord.ButtonStyle.secondary,
            )
        )
        container.add_item(row2)

        row3 = discord.ui.ActionRow()
        if self.campaign.active:
            row3.add_item(
                ActionButton(
                    handler=self._finish,
                    label="Finish campaign",
                    style=discord.ButtonStyle.danger,
                )
            )
        row3.add_item(
            ActionButton(
                handler=self._delete,
                label="Delete campaign",
                style=discord.ButtonStyle.danger,
            )
        )
        container.add_item(row3)

        row4 = discord.ui.ActionRow()
        row4.add_item(
            ActionButton(
                handler=self._back, label="Back", style=discord.ButtonStyle.secondary
            )
        )
        container.add_item(row4)

        self.add_item(container)

    async def _history(self, interaction: discord.Interaction) -> None:
        view = await CampaignHistoryView.create(self.store, self.campaign)
        view.message = interaction.message
        await interaction.response.edit_message(view=view)

    async def _upcoming(self, interaction: discord.Interaction) -> None:
        view = await CampaignUpcomingView.create(self.store, self.campaign)
        view.message = interaction.message
        await interaction.response.edit_message(view=view)

    async def _add_session(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            AddSessionModal(self.store, self.campaign, self)
        )

    async def _edit_rrule(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            EditRRuleModal(self.store, self.campaign, self)
        )

    async def _finish(self, interaction: discord.Interaction) -> None:
        confirm = ConfirmView(
            f"Finish **{self.campaign.name}**?\nNo more sessions will be scheduled."
        )
        await interaction.response.edit_message(view=confirm)
        confirm.message = await interaction.original_response()
        await confirm.wait()
        if confirm.confirmed:
            await self.store.finish_campaign(self.campaign.id)
            self.campaign = await self.store.get_campaign(self.campaign.id)
            self._build()
        await interaction.edit_original_response(view=self)

    async def _delete(self, interaction: discord.Interaction) -> None:
        confirm = ConfirmView(
            f"Delete **{self.campaign.name}**? This cannot be undone."
        )
        await interaction.response.edit_message(view=confirm)
        confirm.message = await interaction.original_response()
        await confirm.wait()
        if confirm.confirmed:
            await self.store.delete_campaign(self.campaign.id)
            view = await CampaignsView.create(self.store)
            view.message = confirm.message
            await interaction.edit_original_response(view=view)
        else:
            await interaction.edit_original_response(view=self)

    async def _back(self, interaction: discord.Interaction) -> None:
        view = await CampaignsView.create(self.store)
        view.message = interaction.message
        await interaction.response.edit_message(view=view)


class CampaignUpcomingView(_PaginatedLayout):
    def __init__(
        self, store: DataStore, campaign: Campaign, sessions: list[Session]
    ) -> None:
        self.store = store
        self.campaign = campaign
        super().__init__(items=sessions)

    def header(self) -> str:
        return f"## {self.campaign.name} — upcoming\n-# Page {self.page + 1}/{self.page_count}"

    def line(self, s: Session) -> str:
        return f"### {session_line(s)}"

    async def on_open(self, interaction: discord.Interaction, s: Session) -> None:
        view = await SessionView.create(
            store=self.store,
            discord_service=interaction.client.discord_service,
            session=s,
            back_factory=lambda: CampaignUpcomingView.create(self.store, self.campaign)
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
        view = CampaignActionsView(self.store, self.campaign)
        view.message = interaction.message
        await interaction.response.edit_message(view=view)

    @classmethod
    async def create(
        cls, store: DataStore, campaign: Campaign, limit: int = 100
    ) -> "CampaignUpcomingView":
        sessions = await store.get_upcoming_campaign_sessions(
            campaign_id=campaign.id, limit=limit
        )
        return cls(store, campaign, sessions)


class CampaignHistoryView(_PaginatedLayout):
    def __init__(
        self, store: DataStore, campaign: Campaign, sessions: list[Session]
    ) -> None:
        self.store = store
        self.campaign = campaign
        super().__init__(items=sessions)
        self._build()

    def header(self) -> str:
        return f"## {self.campaign.name} — History\n-# Page {self.page + 1}/{self.page_count}"

    def line(self, s: Session) -> str:
        return f"### {session_line(s)}"

    async def on_open(self, interaction: discord.Interaction, s: Session) -> None:
        view = await SessionView.create(
            store=self.store,
            discord_service=interaction.client.discord_service,
            session=s,
            back_factory=lambda: CampaignHistoryView.create(self.store, self.campaign)
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
        view = CampaignActionsView(self.store, self.campaign)
        view.message = interaction.message
        await interaction.response.edit_message(view=view)

    @classmethod
    async def create(
        cls, store: DataStore, campaign: Campaign, limit: int = HISTORY_LIMIT
    ) -> "CampaignHistoryView":
        sessions = await store.get_campaign_sessions_history(campaign.id, limit=limit)
        sessions.sort(key=lambda s: s.starts_at, reverse=False)
        return cls(store, campaign, sessions)


class AddSessionModal(discord.ui.Modal, title="Add session"):
    starts_at: discord.ui.TextInput = discord.ui.TextInput(
        label="Start time",
        placeholder="e.g. 2026-09-20 15:00  (parsed as UTC)",
        required=True,
        max_length=100,
    )

    def __init__(
        self, store: DataStore, campaign: Campaign, actions_view: "CampaignActionsView"
    ) -> None:
        super().__init__()
        self.store = store
        self.campaign = campaign
        self.actions_view = actions_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            starts_at = parse_datetime(self.starts_at.value)
        except (ValueError, OverflowError):
            await interaction.response.send_message(
                f"Couldn't understand `{self.starts_at.value}` as a date/time.",
                ephemeral=True,
            )
            return
        session = Session(starts_at=starts_at, campaign_id=self.campaign.id)
        await self.store.add_session(self.campaign.id, session)
        self.actions_view._build()
        await interaction.response.edit_message(view=self.actions_view)


class AddCampaignModal(discord.ui.Modal, title="Add campaign"):
    name: discord.ui.TextInput = discord.ui.TextInput(
        label="Campaign name",
        placeholder="Pathfinder Society",
        required=True,
        max_length=100,
    )

    rrule: discord.ui.TextInput = discord.ui.TextInput(
        label="Recurrence rule (leave empty for oneshots)",
        default="FREQ=WEEKLY;BYDAY=SA;INTERVAL=2",
        placeholder="FREQ=WEEKLY;BYDAY=SA;INTERVAL=2",
        required=False,
        max_length=200,
    )

    def __init__(self, store: DataStore) -> None:
        super().__init__()
        self.store = store

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.rrule.value.strip()
        if value:
            try:
                rrulestr(value)
            except (ValueError, TypeError):
                await interaction.response.send_message(
                    f"Couldn't parse rrule: `{value}`", ephemeral=True
                )
                return
        campaign = Campaign(
            name=self.name.value, rrule=value, started_at=datetime.now(UTC)
        )
        await self.store.add_campaign(campaign)
        if campaign.rrule:
            await self.store.schedule_campaign_sessions(
                campaign.id, count=CONFIG.SESSIONS_PLANNING_WINDOW
            )

        view = await CampaignsView.create(self.store)
        await interaction.response.edit_message(view=view)
        view.message = await interaction.original_response()


class EditRRuleModal(discord.ui.Modal, title="Edit recurrence rule"):
    def __init__(
        self, store: DataStore, campaign: Campaign, actions_view: "CampaignActionsView"
    ) -> None:
        super().__init__()
        self.store = store
        self.campaign = campaign
        self.actions_view = actions_view

        self.rrule: discord.ui.TextInput = discord.ui.TextInput(
            label="Recurrence rule",
            default=campaign.rrule,
            placeholder="FREQ=WEEKLY;BYDAY=SA",
            required=False,
            max_length=200,
        )
        self.add_item(self.rrule)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.rrule.value.strip()
        if value:
            try:
                rrulestr(value)
            except (ValueError, TypeError):
                await interaction.response.send_message(
                    f"`{value}` is not a valid rrule.", ephemeral=True
                )
                return
        await self.store.set_campaign_rrule(self.campaign.id, value)
        self.actions_view._build()
        await interaction.response.edit_message(view=self.actions_view)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception(error)
