from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from . import botauth, domain
from .discord_models import (
    ApplicationCommand,
    ApplicationCommandInteractionDataOption,
    ApplicationCommandOption,
    ApplicationCommandOptionChoice,
    CHANNEL_TYPE_GUILD_STAGE_VOICE,
    CHANNEL_TYPE_GUILD_TEXT,
    CHANNEL_TYPE_GUILD_VOICE,
    INTERACTION_APPLICATION_COMMAND,
    InteractionCreate,
    InteractionResponse,
    InteractionResponseData,
    MessageEmbed,
    OPTION_TYPE_CHANNEL,
    OPTION_TYPE_INTEGER,
    OPTION_TYPE_STRING,
    OPTION_TYPE_SUB_COMMAND,
    OPTION_TYPE_SUB_COMMAND_GROUP,
    PERMISSION_ADMINISTRATOR,
    PERMISSION_MANAGE_GUILD,
)
from .timeutil import discord_timestamp, go_duration

logger = logging.getLogger(__name__)

VOICE_COMMAND_NAME = "voice"
VOICE_INSPECT_HISTORY_COMMAND_NAME = "history"
VOICE_INSPECT_RECENT_SESSION_COMMAND_NAME = "recent-session"
MAX_CLOSED_HISTORY_ITEMS = 10


class Repository(Protocol):
    def get_guild_settings(self, ctx: Any, guild_id: str) -> domain.GuildSettings | None: ...

    def upsert_guild_settings(self, ctx: Any, settings: domain.GuildSettings) -> None: ...

    def list_active_sessions_by_guild(self, ctx: Any, guild_id: str) -> list[domain.Session]: ...

    def find_active_session(self, ctx: Any, guild_id: str, channel_id: str) -> domain.Session | None: ...

    def list_active_participants_by_guild_session(
        self, ctx: Any, guild_id: str, session_id: str
    ) -> list[domain.ParticipantInterval]: ...

    def list_closed_sessions_by_guild_channel(
        self, ctx: Any, guild_id: str, channel_id: str, limit: int
    ) -> list[domain.Session]: ...

    def list_participants_by_guild_channel_session(
        self, ctx: Any, guild_id: str, channel_id: str, session_id: str
    ) -> list[domain.ParticipantInterval]: ...


@dataclass(slots=True)
class SessionParticipantView:
    user_id: str
    user_name: str
    joined_at: datetime
    active_for: timedelta


@dataclass(slots=True)
class ActiveSessionView:
    session: domain.Session
    participants: list[SessionParticipantView] = field(default_factory=list)
    active_for: timedelta = field(default_factory=timedelta)
    count: int = 0


@dataclass(slots=True)
class Service:
    repo: Repository | None = None

    def get_guild_settings(self, ctx: Any, guild_id: str) -> domain.GuildSettings:
        if self.repo is None:
            return domain.new_guild_settings(guild_id, domain.GUILD_TRACKING_MODE_ALL, None, "")
        settings = self.repo.get_guild_settings(ctx, guild_id)
        if settings is None:
            return domain.new_guild_settings(guild_id, domain.GUILD_TRACKING_MODE_ALL, None, "")
        return settings

    def set_tracking_mode(self, ctx: Any, guild_id: str, mode: str) -> domain.GuildSettings:
        settings = self.get_guild_settings(ctx, guild_id)
        settings.tracking_mode = domain.normalize_tracking_mode(mode)
        self._save(ctx, settings)
        return settings

    def set_tracked_channel_ids(self, ctx: Any, guild_id: str, ids: list[str]) -> domain.GuildSettings:
        settings = self.get_guild_settings(ctx, guild_id)
        settings.tracked_channel_ids = domain.clean_channel_ids(ids)
        settings.tracking_mode = (
            domain.GUILD_TRACKING_MODE_NONE
            if len(settings.tracked_channel_ids) == 0
            else domain.GUILD_TRACKING_MODE_SPECIFIC
        )
        self._save(ctx, settings)
        return settings

    def add_tracked_channel(self, ctx: Any, guild_id: str, channel_id: str) -> domain.GuildSettings:
        settings = self.get_guild_settings(ctx, guild_id)
        current_mode = domain.normalize_tracking_mode(settings.tracking_mode)
        channel_id = (channel_id or "").strip()
        if not channel_id:
            raise ValueError("channel id is required")
        settings.tracked_channel_ids = domain.clean_channel_ids([*settings.tracked_channel_ids, channel_id])
        if current_mode == domain.GUILD_TRACKING_MODE_ALL:
            settings.tracking_mode = domain.GUILD_TRACKING_MODE_ALL
        elif len(settings.tracked_channel_ids) == 0:
            settings.tracking_mode = domain.GUILD_TRACKING_MODE_NONE
        else:
            settings.tracking_mode = domain.GUILD_TRACKING_MODE_SPECIFIC
        self._save(ctx, settings)
        return settings

    def remove_tracked_channel(self, ctx: Any, guild_id: str, channel_id: str) -> domain.GuildSettings:
        settings = self.get_guild_settings(ctx, guild_id)
        channel_id = (channel_id or "").strip()
        if not channel_id:
            raise ValueError("channel id is required")
        settings.tracked_channel_ids = _remove_channel_id(settings.tracked_channel_ids, channel_id)
        if domain.normalize_tracking_mode(settings.tracking_mode) != domain.GUILD_TRACKING_MODE_ALL:
            settings.tracking_mode = (
                domain.GUILD_TRACKING_MODE_NONE
                if len(settings.tracked_channel_ids) == 0
                else domain.GUILD_TRACKING_MODE_SPECIFIC
            )
        self._save(ctx, settings)
        return settings

    def clear_tracked_channels(self, ctx: Any, guild_id: str) -> domain.GuildSettings:
        settings = self.get_guild_settings(ctx, guild_id)
        current_mode = domain.normalize_tracking_mode(settings.tracking_mode)
        settings.tracked_channel_ids = []
        if current_mode != domain.GUILD_TRACKING_MODE_ALL:
            settings.tracking_mode = domain.GUILD_TRACKING_MODE_NONE
        self._save(ctx, settings)
        return settings

    def list_tracked_channels(self, ctx: Any, guild_id: str) -> domain.GuildSettings:
        return self.get_guild_settings(ctx, guild_id)

    def set_summary_channel(self, ctx: Any, guild_id: str, channel_id: str) -> domain.GuildSettings:
        settings = self.get_guild_settings(ctx, guild_id)
        settings.summary_channel_id = (channel_id or "").strip()
        self._save(ctx, settings)
        return settings

    def clear_summary_channel(self, ctx: Any, guild_id: str) -> domain.GuildSettings:
        return self.set_summary_channel(ctx, guild_id, "")

    def describe_settings(self, settings: domain.GuildSettings) -> str:
        mode = domain.normalize_tracking_mode(settings.tracking_mode)
        tracked = "all voice channels"
        stored = _channel_mentions(domain.clean_channel_ids(settings.tracked_channel_ids))
        if mode == domain.GUILD_TRACKING_MODE_NONE:
            tracked = "no voice channels"
        elif mode == domain.GUILD_TRACKING_MODE_SPECIFIC:
            tracked = stored
            if not tracked:
                tracked = "no configured channels"

        summary_channel = settings.summary_channel_id.strip()
        summary_channel = _channel_mention(summary_channel) if summary_channel else "not set"

        lines = [f"tracking mode: {mode}", f"tracked channels: {tracked}"]
        if stored and stored != tracked:
            lines.append(f"stored channels: {stored}")
        lines.append(f"summary channel: {summary_channel}")
        return "\n".join(lines)

    def list_active_sessions(self, ctx: Any, guild_id: str) -> list[ActiveSessionView]:
        if self.repo is None:
            return []
        sessions = self.repo.list_active_sessions_by_guild(ctx, guild_id)
        views = [self._build_active_session_view(ctx, session.guild_id, session) for session in sessions]
        views.sort(key=lambda view: view.session.channel_id)
        views.sort(key=lambda view: _time_sort_key(view.session.started_at), reverse=True)
        return views

    def inspect_active_session(self, ctx: Any, guild_id: str, channel_id: str) -> ActiveSessionView | None:
        if self.repo is None:
            return None
        session = self.repo.find_active_session(ctx, guild_id, channel_id)
        if session is None:
            return None
        return self._build_active_session_view(ctx, guild_id, session)

    def describe_active_sessions(self, ctx: Any, guild_id: str) -> str:
        views = self.list_active_sessions(ctx, guild_id)
        if len(views) == 0:
            return "No active sessions."
        lines = ["Active sessions"]
        limit = min(len(views), 10)
        for index in range(limit):
            view = views[index]
            lines.append(f"- <#{view.session.channel_id}>: {view.count} users, running {format_duration(view.active_for)}")
        if len(views) > limit:
            lines.append(f"+{len(views) - limit} more sessions")
        return "\n".join(lines).strip()

    def describe_active_session(self, ctx: Any, guild_id: str, channel_id: str) -> str:
        view = self.inspect_active_session(ctx, guild_id, channel_id)
        if view is None:
            return "No active session in that channel."
        lines = [
            f"Channel: <#{view.session.channel_id}>",
            f"Started: {format_time(view.session.started_at)}",
            f"Running: {format_duration(view.active_for)}",
            f"Participants: {view.count}",
        ]
        if len(view.participants) == 0:
            lines.append("- no active participants")
        else:
            limit = min(len(view.participants), 10)
            for index in range(limit):
                participant = view.participants[index]
                name = participant.user_name or participant.user_id
                lines.append(f"- {name}: {format_duration(participant.active_for)} (joined {format_time(participant.joined_at)})")
            if len(view.participants) > limit:
                lines.append(f"+{len(view.participants) - limit} more participants")
        return "\n".join(lines).strip()

    def describe_closed_session_history(self, ctx: Any, guild_id: str, channel_id: str, limit: int) -> str:
        guild_id = (guild_id or "").strip()
        if not guild_id:
            raise ValueError("guild id is required")
        channel_id = (channel_id or "").strip()
        if not channel_id:
            raise ValueError("channel id is required")
        if limit < 1 or limit > MAX_CLOSED_HISTORY_ITEMS:
            raise ValueError(f"limit must be between 1 and {MAX_CLOSED_HISTORY_ITEMS}")
        if self.repo is None:
            return f"No closed sessions for <#{channel_id}>."
        sessions = self.repo.list_closed_sessions_by_guild_channel(ctx, guild_id, channel_id, limit + 1)
        filtered = [
            session
            for session in sessions
            if session.guild_id == guild_id and session.channel_id == channel_id and session.status == domain.SESSION_STATUS_CLOSED
        ]
        if len(filtered) == 0:
            return f"No closed sessions for <#{channel_id}>."
        has_more = len(filtered) > limit
        if has_more:
            filtered = filtered[:limit]
        lines = [f"Recent closed sessions for <#{channel_id}>"]
        for index, session in enumerate(filtered, start=1):
            participants = self.repo.list_participants_by_guild_channel_session(ctx, guild_id, channel_id, session.id)
            summary = domain.build_session_summary(session, participants, session.ended_by_user_id)
            lines.append(
                f"{index}. ended {format_relative_time(_time_or_zero(session.ended_at))}, duration {format_duration(summary.total_duration)}, {summary.unique_users} users"
            )
        if has_more:
            lines.append("More sessions available.")
        lines.append(f"Use /voice inspect recent-session channel:<#{channel_id}> pick:<number> for details.")
        return "\n".join(lines).strip()

    def describe_closed_session_detail(self, ctx: Any, guild_id: str, channel_id: str, pick: int) -> str:
        guild_id = (guild_id or "").strip()
        if not guild_id:
            raise ValueError("guild id is required")
        channel_id = (channel_id or "").strip()
        if not channel_id:
            raise ValueError("channel id is required")
        if pick < 1 or pick > MAX_CLOSED_HISTORY_ITEMS:
            raise ValueError(f"pick must be between 1 and {MAX_CLOSED_HISTORY_ITEMS}")
        if self.repo is None:
            return f"No closed session #{pick} for <#{channel_id}>."
        sessions = self.repo.list_closed_sessions_by_guild_channel(ctx, guild_id, channel_id, pick)
        filtered = [
            session
            for session in sessions
            if session.guild_id == guild_id and session.channel_id == channel_id and session.status == domain.SESSION_STATUS_CLOSED
        ]
        if len(filtered) < pick:
            return f"No closed session #{pick} for <#{channel_id}>."
        session = filtered[pick - 1]
        participants = self.repo.list_participants_by_guild_channel_session(ctx, guild_id, channel_id, session.id)
        summary = domain.build_session_summary(session, participants, session.ended_by_user_id)
        lines = [
            f"Closed session for <#{channel_id}> (#{pick} most recent)",
            f"Session ID: {session.id}",
            f"Started: {format_time(session.started_at)}",
            f"Ended: {format_time(_time_or_zero(session.ended_at))}",
            f"Duration: {format_duration(summary.total_duration)}",
            f"Unique users: {summary.unique_users}",
        ]
        if session.ended_by_user_id:
            lines.append(f"Ended by: {participant_display_name(summary.participants, session.ended_by_user_id)}")
        lines.extend(["", "Participants"])
        if len(summary.participants) == 0:
            lines.append("- none")
        for participant in summary.participants:
            name = participant.user_name or participant.user_id
            lines.append(f"- {name} - {format_duration(participant.total_time)} ({interval_label(participant.intervals)})")
        return "\n".join(lines).strip()

    def _build_active_session_view(self, ctx: Any, guild_id: str, session: domain.Session) -> ActiveSessionView:
        if self.repo is None:
            participants = []
        else:
            participants = self.repo.list_active_participants_by_guild_session(ctx, guild_id, session.id)
        now = datetime.now(timezone.utc)
        view = ActiveSessionView(session=session, active_for=now - session.started_at, count=len(participants))
        for participant in participants:
            view.participants.append(
                SessionParticipantView(
                    user_id=participant.user_id,
                    user_name=participant.user_name,
                    joined_at=participant.joined_at,
                    active_for=now - participant.joined_at,
                )
            )
        view.participants.sort(key=lambda item: (item.joined_at, item.user_name))
        return view

    def _save(self, ctx: Any, settings: domain.GuildSettings) -> None:
        if self.repo is None:
            return
        settings.guild_id = settings.guild_id.strip()
        settings.tracking_mode = domain.normalize_tracking_mode(settings.tracking_mode)
        settings.tracked_channel_ids = domain.clean_channel_ids(settings.tracked_channel_ids)
        self.repo.upsert_guild_settings(ctx, settings)

    def install(self, session: Any, allowed_guild_id: str, bot_admin_user_ids: list[str]) -> Any:
        def handler(ds: Any, interaction: InteractionCreate) -> None:
            if interaction.type != INTERACTION_APPLICATION_COMMAND:
                return None
            if interaction.guild_id == "":
                respond_ephemeral(ds, interaction, "This command can only be used in a server.")
                return None
            if not allowed_guild_id.strip() or interaction.guild_id != allowed_guild_id:
                return None

            data = interaction.application_command_data()
            if data.name != VOICE_COMMAND_NAME:
                return None

            group, command, options = parse_voice_route(data.options)
            if not can_use_voice_command(interaction, bot_admin_user_ids, group, command):
                respond_ephemeral(ds, interaction, "Insufficient permissions.")
                return None

            try:
                content = self.handle_voice_command(None, interaction, group, command, options)
            except ValueError as exc:
                content = str(exc)
            except Exception:
                logger.exception("voice command failed")
                content = "Command failed. Check service logs."
            if not content:
                content = "Done."
            respond_ephemeral(ds, interaction, content)
            return None

        if hasattr(session, "add_handler"):
            session.add_handler(handler)
        return handler

    def handle_voice_command(
        self,
        ctx: Any,
        interaction: InteractionCreate,
        group: str,
        command: str,
        options: list[ApplicationCommandInteractionDataOption],
    ) -> str:
        if group == "config":
            return self.handle_config_command(ctx, interaction, command, options)
        if group == "inspect":
            return self.handle_inspect_command(ctx, interaction, command, options)
        raise ValueError("unknown command group")

    def handle_config_command(
        self,
        ctx: Any,
        interaction: InteractionCreate,
        command: str,
        options: list[ApplicationCommandInteractionDataOption],
    ) -> str:
        if command == "mode":
            action = option_string(options, "action")
            if action == "show":
                settings = self.get_guild_settings(ctx, interaction.guild_id)
                return f"tracking mode: {domain.normalize_tracking_mode(settings.tracking_mode)}"
            if action == "set":
                mode = option_string(options, "value")
                if not mode:
                    raise ValueError("mode value is required")
                settings = self.set_tracking_mode(ctx, interaction.guild_id, mode)
                return self.describe_settings(settings)
            raise ValueError("unknown mode action")
        if command == "channels":
            action = option_string(options, "action")
            if action == "add":
                channel_id = resolve_command_channel(
                    interaction, options, "channel", CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE
                )
                settings = self.add_tracked_channel(ctx, interaction.guild_id, channel_id)
                return self.describe_settings(settings)
            if action == "remove":
                channel_id = resolve_command_channel(
                    interaction, options, "channel", CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE
                )
                settings = self.remove_tracked_channel(ctx, interaction.guild_id, channel_id)
                return self.describe_settings(settings)
            if action == "list":
                settings = self.list_tracked_channels(ctx, interaction.guild_id)
                return self.describe_settings(settings)
            if action == "clear":
                settings = self.clear_tracked_channels(ctx, interaction.guild_id)
                return self.describe_settings(settings)
            raise ValueError("unknown channels action")
        if command == "summary-channel":
            action = option_string(options, "action")
            if action == "set":
                channel_id = resolve_command_channel(interaction, options, "channel", CHANNEL_TYPE_GUILD_TEXT)
                settings = self.set_summary_channel(ctx, interaction.guild_id, channel_id)
                return self.describe_settings(settings)
            if action == "clear":
                settings = self.clear_summary_channel(ctx, interaction.guild_id)
                return self.describe_settings(settings)
            raise ValueError("unknown summary-channel action")
        raise ValueError("unknown config command")

    def handle_inspect_command(
        self,
        ctx: Any,
        interaction: InteractionCreate,
        command: str,
        options: list[ApplicationCommandInteractionDataOption],
    ) -> str:
        if command == "settings":
            settings = self.get_guild_settings(ctx, interaction.guild_id)
            return self.describe_settings(settings)
        if command == "sessions":
            return self.describe_active_sessions(ctx, interaction.guild_id)
        if command == "session":
            channel_id = resolve_command_channel(interaction, options, "channel", CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE)
            return self.describe_active_session(ctx, interaction.guild_id, channel_id)
        if command == VOICE_INSPECT_HISTORY_COMMAND_NAME:
            channel_id = resolve_command_channel(interaction, options, "channel", CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE)
            limit = option_int_in_range(options, "limit", 5, 1, MAX_CLOSED_HISTORY_ITEMS)
            return self.describe_closed_session_history(ctx, interaction.guild_id, channel_id, limit)
        if command == VOICE_INSPECT_RECENT_SESSION_COMMAND_NAME:
            channel_id = resolve_command_channel(interaction, options, "channel", CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE)
            pick = option_int_in_range(options, "pick", 1, 1, MAX_CLOSED_HISTORY_ITEMS)
            return self.describe_closed_session_detail(ctx, interaction.guild_id, channel_id, pick)
        raise ValueError("unknown inspect command")


def voice_application_command() -> ApplicationCommand:
    return ApplicationCommand(
        name=VOICE_COMMAND_NAME,
        description="Manage tracked voice channels and inspect live and closed sessions",
        options=[
            ApplicationCommandOption(
                type=OPTION_TYPE_SUB_COMMAND_GROUP,
                name="config",
                description="Configure voice tracking",
                options=[
                    ApplicationCommandOption(
                        type=OPTION_TYPE_SUB_COMMAND,
                        name="mode",
                        description="Show or set the tracking mode",
                        options=[
                            ApplicationCommandOption(
                                type=OPTION_TYPE_STRING,
                                name="action",
                                description="show or set",
                                required=True,
                                choices=[
                                    ApplicationCommandOptionChoice(name="show", value="show"),
                                    ApplicationCommandOptionChoice(name="set", value="set"),
                                ],
                            ),
                            ApplicationCommandOption(
                                type=OPTION_TYPE_STRING,
                                name="value",
                                description="all, none, or specific",
                                choices=[
                                    ApplicationCommandOptionChoice(name=domain.GUILD_TRACKING_MODE_ALL, value=domain.GUILD_TRACKING_MODE_ALL),
                                    ApplicationCommandOptionChoice(name=domain.GUILD_TRACKING_MODE_NONE, value=domain.GUILD_TRACKING_MODE_NONE),
                                    ApplicationCommandOptionChoice(name=domain.GUILD_TRACKING_MODE_SPECIFIC, value=domain.GUILD_TRACKING_MODE_SPECIFIC),
                                ],
                            ),
                        ],
                    ),
                    ApplicationCommandOption(
                        type=OPTION_TYPE_SUB_COMMAND,
                        name="channels",
                        description="Manage tracked voice channels",
                        options=[
                            ApplicationCommandOption(
                                type=OPTION_TYPE_STRING,
                                name="action",
                                description="add, remove, list, or clear",
                                required=True,
                                choices=[
                                    ApplicationCommandOptionChoice(name="add", value="add"),
                                    ApplicationCommandOptionChoice(name="remove", value="remove"),
                                    ApplicationCommandOptionChoice(name="list", value="list"),
                                    ApplicationCommandOptionChoice(name="clear", value="clear"),
                                ],
                            ),
                            ApplicationCommandOption(
                                type=OPTION_TYPE_CHANNEL,
                                name="channel",
                                description="Voice channel",
                                channel_types=[CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE],
                            ),
                        ],
                    ),
                    ApplicationCommandOption(
                        type=OPTION_TYPE_SUB_COMMAND,
                        name="summary-channel",
                        description="Set or clear the summary destination",
                        options=[
                            ApplicationCommandOption(
                                type=OPTION_TYPE_STRING,
                                name="action",
                                description="set or clear",
                                required=True,
                                choices=[
                                    ApplicationCommandOptionChoice(name="set", value="set"),
                                    ApplicationCommandOptionChoice(name="clear", value="clear"),
                                ],
                            ),
                            ApplicationCommandOption(
                                type=OPTION_TYPE_CHANNEL,
                                name="channel",
                                description="Destination text channel",
                                channel_types=[CHANNEL_TYPE_GUILD_TEXT],
                            ),
                        ],
                    ),
                ],
            ),
            ApplicationCommandOption(
                type=OPTION_TYPE_SUB_COMMAND_GROUP,
                name="inspect",
                description="Inspect live and closed voice sessions",
                options=[
                    ApplicationCommandOption(type=OPTION_TYPE_SUB_COMMAND, name="settings", description="Show current settings"),
                    ApplicationCommandOption(type=OPTION_TYPE_SUB_COMMAND, name="sessions", description="List active sessions (Admin only)"),
                    ApplicationCommandOption(
                        type=OPTION_TYPE_SUB_COMMAND,
                        name="session",
                        description="Inspect one active session (Admin only)",
                        options=[
                            ApplicationCommandOption(
                                type=OPTION_TYPE_CHANNEL,
                                name="channel",
                                description="Tracked voice channel",
                                required=True,
                                channel_types=[CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE],
                            )
                        ],
                    ),
                    ApplicationCommandOption(
                        type=OPTION_TYPE_SUB_COMMAND,
                        name=VOICE_INSPECT_HISTORY_COMMAND_NAME,
                        description="List recent closed sessions for one voice channel",
                        options=[
                            ApplicationCommandOption(
                                type=OPTION_TYPE_CHANNEL,
                                name="channel",
                                description="Voice channel to inspect",
                                required=True,
                                channel_types=[CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE],
                            ),
                            ApplicationCommandOption(
                                type=OPTION_TYPE_INTEGER,
                                name="limit",
                                description="How many closed sessions to show (1-10)",
                            ),
                        ],
                    ),
                    ApplicationCommandOption(
                        type=OPTION_TYPE_SUB_COMMAND,
                        name=VOICE_INSPECT_RECENT_SESSION_COMMAND_NAME,
                        description="Inspect one recent closed session for a voice channel",
                        options=[
                            ApplicationCommandOption(
                                type=OPTION_TYPE_CHANNEL,
                                name="channel",
                                description="Voice channel to inspect",
                                required=True,
                                channel_types=[CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE],
                            ),
                            ApplicationCommandOption(
                                type=OPTION_TYPE_INTEGER,
                                name="pick",
                                description="Which recent closed session to inspect (1-10)",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def parse_voice_route(
    options: list[ApplicationCommandInteractionDataOption],
) -> tuple[str, str, list[ApplicationCommandInteractionDataOption]]:
    if len(options) == 0:
        return "", "", []
    group_opt = options[0]
    group = group_opt.name
    if len(group_opt.options) == 0:
        return group, "", []
    command_opt = group_opt.options[0]
    return group, command_opt.name, list(command_opt.options)


def can_use_voice_command(
    interaction: InteractionCreate | None, bot_admin_user_ids: list[str], group: str, command: str
) -> bool:
    if botauth.is_allowlisted(interaction, bot_admin_user_ids):
        return True
    if group == "inspect" and (command == "sessions" or command == "session"):
        return has_administrator_permissions(interaction)
    if group == "inspect" and (command == VOICE_INSPECT_HISTORY_COMMAND_NAME or command == VOICE_INSPECT_RECENT_SESSION_COMMAND_NAME):
        return has_administrator_permissions(interaction)
    return has_manage_permissions(interaction)


def option_string(options: list[ApplicationCommandInteractionDataOption], name: str) -> str:
    for option in options:
        if option.name == name and isinstance(option.value, str):
            return option.value.strip()
    return ""


def option_channel_id(options: list[ApplicationCommandInteractionDataOption], name: str) -> str:
    return option_string(options, name)


def option_int_in_range(
    options: list[ApplicationCommandInteractionDataOption], name: str, fallback: int, min_value: int, max_value: int
) -> int:
    if fallback < min_value or fallback > max_value:
        raise ValueError(f"invalid default for {name}")
    for option in options:
        if option.name != name:
            continue
        value = option.value
        if isinstance(value, bool):
            raise ValueError(f"invalid {name} value")
        if isinstance(value, int):
            if value < min_value or value > max_value:
                raise ValueError(f"{name} must be between {min_value} and {max_value}")
            return value
        if isinstance(value, float):
            if math.trunc(value) != value:
                raise ValueError(f"{name} must be a whole number")
            int_value = int(value)
            if int_value < min_value or int_value > max_value:
                raise ValueError(f"{name} must be between {min_value} and {max_value}")
            return int_value
        raise ValueError(f"invalid {name} value")
    return fallback


def resolve_command_channel(
    interaction: InteractionCreate,
    options: list[ApplicationCommandInteractionDataOption],
    name: str,
    *allowed_types: str,
) -> str:
    channel_id = option_channel_id(options, name)
    if not channel_id:
        raise ValueError("channel is required")
    resolved = interaction.application_command_data().resolved
    if resolved is None or resolved.channels is None:
        raise ValueError("channel resolution unavailable")
    channel = resolved.channels.get(channel_id)
    if channel is None:
        raise ValueError("unable to resolve channel")
    if channel.guild_id and channel.guild_id != interaction.guild_id:
        raise ValueError("channel must belong to this guild")
    if len(allowed_types) > 0 and not channel_type_allowed(channel.type, *allowed_types):
        raise ValueError("unsupported channel type")
    return channel_id


def channel_type_allowed(channel_type: str, *allowed_types: str) -> bool:
    normalized = _channel_type_value(channel_type)
    return any(normalized == _channel_type_value(allowed) for allowed in allowed_types)


def _channel_type_value(value: Any) -> Any:
    if hasattr(value, "value") and not isinstance(value, (str, bytes, bytearray)):
        return value.value
    return {"guild_text": 0, "guild_voice": 2, "guild_stage_voice": 13}.get(value, value)


def has_manage_permissions(interaction: InteractionCreate | None) -> bool:
    if interaction is None or interaction.member is None:
        return False
    permissions = interaction.member.permissions
    return bool(permissions & (PERMISSION_ADMINISTRATOR | PERMISSION_MANAGE_GUILD))


def has_administrator_permissions(interaction: InteractionCreate | None) -> bool:
    if interaction is None or interaction.member is None:
        return False
    return bool(interaction.member.permissions & PERMISSION_ADMINISTRATOR)


def respond_ephemeral(session: Any, interaction: InteractionCreate, content: str) -> InteractionResponse:
    response = InteractionResponse(
        data=InteractionResponseData(
            flags=1 << 6,
            embeds=[MessageEmbed(title="Voice Tracker", description=content, color=0x5865F2)],
        )
    )
    if hasattr(session, "interaction_respond"):
        session.interaction_respond(interaction.interaction, response)
    return response


def format_duration(value: timedelta) -> str:
    if value.total_seconds() < 0:
        value = timedelta()
    return go_duration(value, round_seconds=True)


def format_time(value: datetime | None) -> str:
    return discord_timestamp(value)


def format_relative_time(value: datetime | None) -> str:
    return discord_timestamp(value, style="relative")


def participant_display_name(participants: list[domain.ParticipantSummary], user_id: str) -> str:
    user_id = (user_id or "").strip()
    if not user_id:
        return "unknown"
    for participant in participants:
        if participant.user_id == user_id and participant.user_name.strip():
            return participant.user_name
    return user_id


def interval_label(count: int) -> str:
    if count == 1:
        return "1 interval"
    return f"{count} intervals"


def _remove_channel_id(ids: list[str], target: str) -> list[str]:
    return [value for value in ids if value.strip() != target]


def _channel_mentions(ids: list[str]) -> str:
    if len(ids) == 0:
        return ""
    return ", ".join(_channel_mention(channel_id) for channel_id in ids)


def _channel_mention(channel_id: str) -> str:
    return f"<#{channel_id}>" if channel_id else ""


def _time_or_zero(value: datetime | None) -> datetime:
    return value


def _time_sort_key(value: datetime | None) -> datetime:
    return value if value is not None else datetime.min.replace(tzinfo=timezone.utc)


VoiceApplicationCommand = voice_application_command
