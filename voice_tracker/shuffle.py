from __future__ import annotations

import inspect
import random
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

try:  # pragma: no cover - exercised in the real app, not in unit tests
    import discord
except Exception:  # pragma: no cover - keeps the module importable in lean test envs
    discord = None  # type: ignore[assignment]


SHUFFLE_COMMAND_NAME = "shuffle"
SHUFFLE_GATHER_GROUP = "gather"
SHUFFLE_EQUAL_GROUP = "equal"

OPTION_SUB_COMMAND_GROUP = "subcommand_group"
OPTION_SUB_COMMAND = "subcommand"
OPTION_CHANNEL = "channel"
OPTION_STRING = "string"

if discord is None:  # pragma: no cover - fallback for import-only environments
    CHANNEL_TYPE_GUILD_VOICE = "guild_voice"
    CHANNEL_TYPE_GUILD_STAGE_VOICE = "guild_stage_voice"
else:  # pragma: no cover - exercised in the real app, not in unit tests
    CHANNEL_TYPE_GUILD_VOICE = discord.ChannelType.voice
    CHANNEL_TYPE_GUILD_STAGE_VOICE = discord.ChannelType.stage_voice


def _permission_value(flag_name: str) -> int:
    if discord is None:  # pragma: no cover - fallback for import-only environments
        fallback_bits = {
            "administrator": 1 << 3,
            "manage_guild": 1 << 5,
            "view_channel": 1 << 10,
            "connect": 1 << 20,
            "move_members": 1 << 24,
        }
        return fallback_bits[flag_name]
    return discord.Permissions(**{flag_name: True}).value


PERMISSION_VIEW_CHANNEL = _permission_value("view_channel")
PERMISSION_VOICE_CONNECT = _permission_value("connect")
PERMISSION_VOICE_MOVE_MEMBERS = _permission_value("move_members")
PERMISSION_ADMINISTRATOR = _permission_value("administrator")
PERMISSION_MANAGE_GUILD = _permission_value("manage_guild")


class Mover(Protocol):
    def guild_member(self, guild_id: str, user_id: str, *args: Any, **kwargs: Any) -> Any:
        ...

    def guild_member_move(self, guild_id: str, user_id: str, channel_id: str | None, *args: Any, **kwargs: Any) -> Any:
        ...

    def user_channel_permissions(self, user_id: str, channel_id: str, *args: Any, **kwargs: Any) -> Any:
        ...


@dataclass(slots=True)
class CommandChoice:
    name: str
    value: Any


@dataclass(slots=True)
class CommandOption:
    type: str
    name: str
    description: str
    required: bool = False
    channel_types: tuple[str, ...] = ()
    choices: tuple[CommandChoice, ...] = ()
    options: tuple["CommandOption", ...] = ()


@dataclass(slots=True)
class ApplicationCommand:
    name: str
    description: str
    options: tuple[CommandOption, ...] = ()
    default_member_permissions: int | None = None


@dataclass(slots=True)
class ChannelResult:
    channel_id: str
    moved: int = 0


@dataclass(slots=True)
class Result:
    movable_users: int = 0
    moved_users: int = 0
    excluded_users: int = 0
    skipped_channels: int = 0
    skipped_channel_ids: list[str] = field(default_factory=list)
    channel_results: list[ChannelResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _maybe_snowflake(value: str) -> Any:
    if re.fullmatch(r"\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def normalize_ids(values: list[str] | tuple[str, ...] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values or []:
        value = _clean(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def without_channel(values: list[str], channel_id: str) -> list[str]:
    channel_id = _clean(channel_id)
    if not channel_id:
        return list(values)
    return [value for value in values if _clean(value) != channel_id]


def channel_type_allowed(channel_type: Any, *allowed_types: Any) -> bool:
    normalized = _channel_type_value(channel_type)
    return any(normalized == _channel_type_value(allowed) for allowed in allowed_types)


def _channel_type_value(value: Any) -> Any:
    if hasattr(value, "value") and not isinstance(value, (str, bytes, bytearray)):
        return value.value
    return {"guild_text": 0, "guild_voice": 2, "guild_stage_voice": 13}.get(value, value)


def balanced_counts(total: int, buckets: int) -> list[int]:
    counts = [0] * buckets
    if buckets == 0:
        return counts
    base, extra = divmod(total, buckets)
    for index in range(buckets):
        counts[index] = base + (1 if index < extra else 0)
    return counts


def format_channel_mentions(channel_ids: list[str]) -> str:
    if not channel_ids:
        return "none"
    mentions = [f"<#{channel_id}>" for channel_id in channel_ids if _clean(channel_id)]
    return ", ".join(mentions) if mentions else "none"


def format_shuffle_result(result: Result) -> str:
    lines: list[str] = []
    if not result.failures:
        lines.append(f"Shuffled {result.moved_users} users across {len(result.channel_results)} channels.")
    else:
        lines.append(
            f"Shuffled {result.moved_users} users across {len(result.channel_results)} channels with {len(result.failures)} move failure(s)."
        )
    if result.excluded_users > 0:
        lines.append(f"Excluded {result.excluded_users} user(s).")
    for channel in result.channel_results:
        lines.append(f"<#{channel.channel_id}>: {channel.moved} moved")
    if result.failures:
        lines.append("Failures:")
        lines.extend(f"- {failure}" for failure in result.failures)
    return "\n".join(lines).strip()


def format_gather_result(destination_channel_id: str, result: Result) -> str:
    lines: list[str] = []
    if not result.failures:
        lines.append(f"Gathered {result.moved_users} users into <#{destination_channel_id}>.")
    else:
        lines.append(
            f"Gathered {result.moved_users} users into <#{destination_channel_id}> with {len(result.failures)} move failure(s)."
        )
    if result.skipped_channels > 0:
        lines.append(
            f"Skipped {result.skipped_channels} inaccessible channel(s): {format_channel_mentions(result.skipped_channel_ids)}."
        )
    if result.excluded_users > 0:
        lines.append(f"Excluded {result.excluded_users} user(s).")
    if result.channel_results:
        channel = result.channel_results[0]
        lines.append(f"<#{channel.channel_id}>: {channel.moved} moved")
    if result.failures:
        lines.append("Failures:")
        lines.extend(f"- {failure}" for failure in result.failures)
    return "\n".join(lines).strip()


def parse_user_id_token(token: str) -> str:
    token = _clean(token)
    if not token:
        raise ValueError("invalid excluded user")
    if token.startswith("<@") and token.endswith(">"):
        token = token.removeprefix("<@!").removeprefix("<@").removesuffix(">")
    if not re.fullmatch(r"\d+", token):
        raise ValueError(f"invalid excluded user {token!r}")
    return token


def parse_excluded_user_ids(raw: str | None) -> list[str] | None:
    raw = _clean(raw)
    if not raw:
        return None
    tokens = [token for token in re.split(r"[\s,;]+", raw) if token]
    ids: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        user_id = parse_user_id_token(token)
        if user_id in seen:
            continue
        seen.add(user_id)
        ids.append(user_id)
    return ids


def parse_shuffle_route(options: list[Any]) -> tuple[str, str, list[Any]]:
    if len(options) == 0:
        return "", "", []
    group_option = options[0]
    group = _option_name(group_option)
    group_options = _option_options(group_option)
    if len(group_options) == 0:
        return group, "", []
    command_option = group_options[0]
    return group, _option_name(command_option), _option_options(command_option)


def option_string(options: list[Any], name: str) -> str:
    for option in options:
        if _option_name(option) == name and isinstance(_option_value(option), str):
            return _option_value(option).strip()
    return ""


def option_channel_id(options: list[Any], name: str) -> str:
    return option_string(options, name)


def resolve_shuffle_channels(interaction: Any, options: list[Any], command: str) -> list[str]:
    required = {
        "two": {"voice1", "voice2"},
        "three": {"voice1", "voice2", "voice3"},
        "four": {"voice1", "voice2", "voice3", "voice4"},
    }.get(command)
    if required is None:
        raise ValueError("unknown shuffle equal command")
    resolved: list[str] = []
    for name in ("voice1", "voice2", "voice3", "voice4"):
        if name not in required:
            continue
        resolved.append(resolve_command_channel(interaction, options, name, CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE))
    return resolved


def resolve_gather_channels(interaction: Any, options: list[Any]) -> list[str]:
    resolved: list[str] = []
    for index in range(1, 9):
        name = f"source{index}"
        try:
            channel_id = resolve_command_channel(interaction, options, name, CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE)
        except ValueError:
            if option_channel_id(options, name) == "":
                continue
            raise
        resolved.append(channel_id)
    if len(resolved) == 0:
        raise ValueError("at least one source channel is required")
    return resolved


def resolve_command_channel(interaction: Any, options: list[Any], name: str, *allowed_types: Any) -> str:
    channel_id = option_channel_id(options, name)
    if not channel_id:
        raise ValueError("channel is required")
    data = interaction.application_command_data() if hasattr(interaction, "application_command_data") else getattr(interaction, "data", None)
    resolved = getattr(data, "resolved", None)
    channels = getattr(resolved, "channels", None)
    if channels is None:
        raise ValueError("channel resolution unavailable")
    channel = channels.get(channel_id)
    if channel is None:
        raise ValueError("unable to resolve channel")
    guild_id = _clean(getattr(interaction, "guild_id", ""))
    channel_guild_id = _clean(getattr(channel, "guild_id", ""))
    if channel_guild_id and channel_guild_id != guild_id:
        raise ValueError("channel must belong to this guild")
    if allowed_types and not channel_type_allowed(getattr(channel, "type", None), *allowed_types):
        raise ValueError("unsupported channel type")
    return channel_id


async def handle_equal_command(service: "Service", interaction: Any, command: str, options: list[Any], ctx: Any | None = None) -> str:
    if command not in {"two", "three", "four"}:
        raise ValueError("unknown shuffle equal command")
    channel_ids = resolve_shuffle_channels(interaction, options, command)
    excluded_ids = parse_excluded_user_ids(option_string(options, "exclude"))
    result = await service.equal(_clean(getattr(interaction, "guild_id", "")), channel_ids, excluded_ids, ctx)
    return format_shuffle_result(result)


async def handle_gather_command(service: "Service", interaction: Any, command: str, options: list[Any], ctx: Any | None = None) -> str:
    if command == "all":
        destination_channel_id = resolve_command_channel(
            interaction, options, "destination", CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE
        )
        excluded_ids = parse_excluded_user_ids(option_string(options, "exclude"))
        result = await service.gather(_clean(getattr(interaction, "guild_id", "")), destination_channel_id, None, excluded_ids, ctx)
        return format_gather_result(destination_channel_id, result)
    if command == "select":
        destination_channel_id = resolve_command_channel(
            interaction, options, "destination", CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE
        )
        source_channel_ids = resolve_gather_channels(interaction, options)
        excluded_ids = parse_excluded_user_ids(option_string(options, "exclude"))
        result = await service.gather(_clean(getattr(interaction, "guild_id", "")), destination_channel_id, source_channel_ids, excluded_ids, ctx)
        return format_gather_result(destination_channel_id, result)
    raise ValueError("unknown shuffle gather command")


def _option_name(option: Any) -> str:
    if isinstance(option, dict):
        return str(option.get("name", ""))
    return str(getattr(option, "name", ""))


def _option_value(option: Any) -> Any:
    if isinstance(option, dict):
        return option.get("value")
    return getattr(option, "value", None)


def _option_options(option: Any) -> list[Any]:
    if isinstance(option, dict):
        return list(option.get("options", []) or [])
    return list(getattr(option, "options", []) or [])


def _extract_permissions(member: Any) -> int | None:
    if member is None:
        return None
    for attr in ("guild_permissions", "permissions"):
        permissions = getattr(member, attr, None)
        if permissions is None:
            continue
        if isinstance(permissions, int):
            return permissions
        value = getattr(permissions, "value", None)
        if isinstance(value, int):
            return value
    return None


def can_use_shuffle_command(interaction: Any, bot_admin_user_ids: list[str] | tuple[str, ...] | None) -> bool:
    if bot_admin_user_ids:
        user = getattr(interaction, "user", None) or getattr(interaction, "member", None)
        user_id = _clean(getattr(user, "id", ""))
        if user_id and user_id in { _clean(user_id_value) for user_id_value in bot_admin_user_ids }:
            return True
    member = getattr(interaction, "member", None) or getattr(interaction, "user", None)
    permissions = _extract_permissions(member)
    if permissions is None:
        return False
    return bool(permissions & (PERMISSION_ADMINISTRATOR | PERMISSION_VOICE_MOVE_MEMBERS))


def shuffle_application_command() -> ApplicationCommand:
    return ApplicationCommand(
        name=SHUFFLE_COMMAND_NAME,
        description="Redistribute people evenly across voice channels",
        options=(
            CommandOption(
                type=OPTION_SUB_COMMAND_GROUP,
                name=SHUFFLE_GATHER_GROUP,
                description="Put everyone back into one voice channel",
                options=(
                    shuffle_gather_all_command(),
                    shuffle_gather_select_command(),
                ),
            ),
            CommandOption(
                type=OPTION_SUB_COMMAND_GROUP,
                name=SHUFFLE_EQUAL_GROUP,
                description="Evenly reshuffle voice channels",
                options=(
                    shuffle_equal_command("two", 2),
                    shuffle_equal_command("three", 3),
                    shuffle_equal_command("four", 4),
                ),
            ),
        ),
    )


def shuffle_equal_command(name: str, channels: int) -> CommandOption:
    options = [
        CommandOption(
            type=OPTION_CHANNEL,
            name=f"voice{index}",
            description=f"Voice channel {index}",
            required=True,
            channel_types=(CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE),
        )
        for index in range(1, channels + 1)
    ]
    options.append(
        CommandOption(
            type=OPTION_STRING,
            name="exclude",
            description="User IDs or mentions to keep in place",
        )
    )
    return CommandOption(
        type=OPTION_SUB_COMMAND,
        name=name,
        description=f"Reshuffle {channels} voice channels",
        options=tuple(options),
    )


def shuffle_gather_all_command() -> CommandOption:
    return CommandOption(
        type=OPTION_SUB_COMMAND,
        name="all",
        description="Gather everyone from every voice channel into one channel",
        options=(
            CommandOption(
                type=OPTION_CHANNEL,
                name="destination",
                description="Voice channel to gather into",
                required=True,
                channel_types=(CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE),
            ),
            CommandOption(
                type=OPTION_STRING,
                name="exclude",
                description="User IDs or mentions to keep in place",
            ),
        ),
    )


def shuffle_gather_select_command() -> CommandOption:
    options = [
        CommandOption(
            type=OPTION_CHANNEL,
            name="destination",
            description="Voice channel to gather into",
            required=True,
            channel_types=(CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE),
        ),
        CommandOption(
            type=OPTION_CHANNEL,
            name="source1",
            description="Voice channel 1",
            required=True,
            channel_types=(CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE),
        ),
    ]
    for index in range(2, 9):
        options.append(
            CommandOption(
                type=OPTION_CHANNEL,
                name=f"source{index}",
                description=f"Voice channel {index}",
                channel_types=(CHANNEL_TYPE_GUILD_VOICE, CHANNEL_TYPE_GUILD_STAGE_VOICE),
            )
        )
    options.append(
        CommandOption(
            type=OPTION_STRING,
            name="exclude",
            description="User IDs or mentions to keep in place",
        )
    )
    return CommandOption(
        type=OPTION_SUB_COMMAND,
        name="select",
        description="Gather members from chosen voice channels into one channel",
        options=tuple(options),
    )


class Service:
    def __init__(self, state: Any, mover: Mover | None, bot_user_id: str, rng: random.Random | None = None) -> None:
        self._state = state
        self._mover = mover
        self._bot_user_id = _clean(bot_user_id)
        self._rng = rng or random.Random()

    async def equal(
        self,
        guild_id: str,
        channel_ids: list[str] | tuple[str, ...] | None,
        excluded_ids: list[str] | tuple[str, ...] | None,
        ctx: Any | None = None,
    ) -> Result:
        _ = ctx
        if self._state is None or self._mover is None:
            raise RuntimeError("shuffle service is unavailable")
        guild_id = _clean(guild_id)
        if not guild_id:
            raise ValueError("guild id is required")

        guild = self._get_guild(guild_id)
        if guild is None:
            raise RuntimeError("guild state is unavailable")

        target_channels = self._normalize_channels(guild, list(channel_ids or ()))
        if len(target_channels) < 2:
            raise ValueError("at least two voice channels are required")
        await self._ensure_permissions(target_channels, ctx)

        excluded_set = {user_id: None for user_id in normalize_ids(list(excluded_ids or ()))}
        users, excluded_count = await self._collect_users(guild_id, guild, target_channels, excluded_set, ctx)
        if len(users) < len(target_channels):
            raise ValueError(
                f"not enough people to shuffle: need at least {len(target_channels)} movable users for {len(target_channels)} channels"
            )

        self._shuffle_strings(users)
        shuffled_channels = list(target_channels)
        self._shuffle_strings(shuffled_channels)
        counts = balanced_counts(len(users), len(shuffled_channels))
        result = Result(
            movable_users=len(users),
            excluded_users=excluded_count,
            channel_results=[],
        )
        remaining = list(users)
        for index, channel_id in enumerate(shuffled_channels):
            channel_result = ChannelResult(channel_id=channel_id)
            slots = counts[index]
            while slots > 0:
                if not remaining:
                    break
                user_id = remaining.pop(0)
                try:
                    await self._guild_member_move(guild_id, user_id, channel_id, ctx)
                except Exception as exc:  # pragma: no cover - exercised through tests
                    result.failures.append(f"<@{user_id}> -> <#{channel_id}>: {exc}")
                    continue
                channel_result.moved += 1
                result.moved_users += 1
                slots -= 1
            result.channel_results.append(channel_result)
        return result

    async def gather(
        self,
        guild_id: str,
        destination_channel_id: str,
        source_channel_ids: list[str] | tuple[str, ...] | None,
        excluded_ids: list[str] | tuple[str, ...] | None,
        ctx: Any | None = None,
    ) -> Result:
        _ = ctx
        if self._state is None or self._mover is None:
            raise RuntimeError("shuffle service is unavailable")
        guild_id = _clean(guild_id)
        if not guild_id:
            raise ValueError("guild id is required")
        destination_channel_id = _clean(destination_channel_id)
        if not destination_channel_id:
            raise ValueError("destination channel is required")

        guild = self._get_guild(guild_id)
        if guild is None:
            raise RuntimeError("guild state is unavailable")

        destination_channel = self._find_channel(guild, destination_channel_id)
        if destination_channel is None:
            raise ValueError(f"unable to resolve destination channel {destination_channel_id}")
        if not channel_type_allowed(
            getattr(destination_channel, "type", None),
            CHANNEL_TYPE_GUILD_VOICE,
            CHANNEL_TYPE_GUILD_STAGE_VOICE,
        ):
            raise ValueError(f"unsupported channel type for <#{destination_channel_id}>")

        if not source_channel_ids:
            source_channels = self._all_voice_channels(guild, destination_channel_id)
        else:
            source_channels = self._normalize_channels(guild, list(source_channel_ids))
            source_channels = without_channel(source_channels, destination_channel_id)
        if not source_channels:
            raise ValueError("at least one source voice channel is required")

        await self._ensure_permissions([destination_channel_id], ctx)
        accessible_sources, skipped_channels, skipped_channel_ids = await self._filter_accessible_channels(source_channels, ctx)
        if not accessible_sources:
            raise ValueError("no accessible voice channels to gather from")

        excluded_set = {user_id: None for user_id in normalize_ids(list(excluded_ids or ()))}
        users, excluded_count = await self._collect_users(guild_id, guild, accessible_sources, excluded_set, ctx)
        if not users:
            raise ValueError("no movable users to gather")

        self._shuffle_strings(users)
        result = Result(
            movable_users=len(users),
            excluded_users=excluded_count,
            skipped_channels=skipped_channels,
            skipped_channel_ids=skipped_channel_ids,
            channel_results=[ChannelResult(channel_id=destination_channel_id)],
        )
        for user_id in users:
            try:
                await self._guild_member_move(guild_id, user_id, destination_channel_id, ctx)
            except Exception as exc:  # pragma: no cover - exercised through tests
                result.failures.append(f"<@{user_id}> -> <#{destination_channel_id}>: {exc}")
                continue
            result.channel_results[0].moved += 1
            result.moved_users += 1
        return result

    def _get_guild(self, guild_id: str) -> Any | None:
        state = self._state
        if state is None:
            return None
        if hasattr(state, "get_guild"):
            for candidate in (_maybe_snowflake(guild_id), guild_id):
                guild = state.get_guild(candidate)
                if guild is not None:
                    return guild
        if hasattr(state, "guild"):
            guild = getattr(state, "guild")
            if getattr(guild, "id", None) == guild_id:
                return guild
        return None

    def _normalize_channels(self, guild: Any, channel_ids: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in channel_ids:
            channel_id = _clean(raw)
            if not channel_id:
                continue
            if channel_id in seen:
                raise ValueError(f"duplicate channel {channel_id}")
            channel = self._find_channel(guild, channel_id)
            if channel is None:
                raise ValueError(f"unable to resolve channel {channel_id}")
            if not channel_type_allowed(
                getattr(channel, "type", None),
                CHANNEL_TYPE_GUILD_VOICE,
                CHANNEL_TYPE_GUILD_STAGE_VOICE,
            ):
                raise ValueError(f"unsupported channel type for <#{channel_id}>")
            seen.add(channel_id)
            out.append(channel_id)
        return out

    def _all_voice_channels(self, guild: Any, *exclude_ids: str) -> list[str]:
        excluded = {user_id for user_id in normalize_ids(list(exclude_ids))}
        channels = []
        for channel in self._iter_channels(guild):
            channel_id = _clean(getattr(channel, "id", ""))
            if not channel_id or channel_id in excluded:
                continue
            if not channel_type_allowed(
                getattr(channel, "type", None),
                CHANNEL_TYPE_GUILD_VOICE,
                CHANNEL_TYPE_GUILD_STAGE_VOICE,
            ):
                continue
            channels.append(channel_id)
        return channels

    async def _ensure_permissions(self, channel_ids: list[str], ctx: Any | None) -> None:
        if not self._bot_user_id:
            raise RuntimeError("bot user id is unavailable")
        for channel_id in normalize_ids(channel_ids):
            perms = await self._user_channel_permissions(self._bot_user_id, channel_id, ctx)
            if perms & PERMISSION_VIEW_CHANNEL == 0:
                raise ValueError(f"missing view channel permission for <#{channel_id}>")
            if perms & PERMISSION_VOICE_CONNECT == 0:
                raise ValueError(f"missing connect permission for <#{channel_id}>")
            if perms & PERMISSION_VOICE_MOVE_MEMBERS == 0:
                raise ValueError(f"missing move members permission for <#{channel_id}>")

    async def _filter_accessible_channels(self, channel_ids: list[str], ctx: Any | None) -> tuple[list[str], int, list[str]]:
        if not self._bot_user_id:
            raise RuntimeError("bot user id is unavailable")
        accessible: list[str] = []
        skipped_ids: list[str] = []
        skipped = 0
        for channel_id in normalize_ids(channel_ids):
            perms = await self._user_channel_permissions(self._bot_user_id, channel_id, ctx)
            if perms & PERMISSION_VIEW_CHANNEL == 0 or perms & PERMISSION_VOICE_CONNECT == 0 or perms & PERMISSION_VOICE_MOVE_MEMBERS == 0:
                skipped += 1
                skipped_ids.append(channel_id)
                continue
            accessible.append(channel_id)
        return accessible, skipped, skipped_ids

    async def _collect_users(
        self,
        guild_id: str,
        guild: Any,
        channel_ids: list[str],
        excluded_set: dict[str, None],
        ctx: Any | None,
    ) -> tuple[list[str], int]:
        targets = set(channel_ids)
        users: list[str] = []
        seen: set[str] = set()
        excluded_count = 0
        for voice_state in self._iter_voice_states(guild):
            if self._voice_state_channel_id(voice_state) not in targets:
                continue
            user_id = self._voice_state_user_id(voice_state)
            if not user_id or user_id == self._bot_user_id:
                continue
            if user_id in excluded_set:
                excluded_count += 1
                continue
            if user_id in seen:
                continue
            if await self._is_bot(guild_id, user_id, ctx):
                continue
            seen.add(user_id)
            users.append(user_id)
        return users, excluded_count

    async def _is_bot(self, guild_id: str, user_id: str, ctx: Any | None) -> bool:
        guild = self._get_guild(guild_id)
        if guild is not None:
            member = self._get_cached_member(guild, user_id)
            if member is not None:
                return self._member_is_bot(member)
        try:
            member = await self._guild_member(guild_id, user_id, ctx)
        except Exception:
            return False
        if member is None:
            return False
        return self._member_is_bot(member)

    @staticmethod
    def _member_is_bot(member: Any) -> bool:
        user = getattr(member, "user", None)
        if user is not None and hasattr(user, "bot"):
            return bool(getattr(user, "bot"))
        if hasattr(member, "bot"):
            return bool(getattr(member, "bot"))
        return False

    def _get_cached_member(self, guild: Any, user_id: str) -> Any | None:
        for attr in ("get_member", "member"):
            accessor = getattr(guild, attr, None)
            if callable(accessor):
                for candidate in (_maybe_snowflake(user_id), user_id):
                    try:
                        member = accessor(candidate)
                    except TypeError:
                        continue
                    if member is not None:
                        return member
        members = getattr(guild, "members", None)
        if members is not None:
            for member in members:
                member_user = getattr(member, "user", None)
                if _clean(getattr(member_user, "id", "")) == user_id or _clean(getattr(member, "id", "")) == user_id:
                    return member
        return None

    def _find_channel(self, guild: Any, channel_id: str) -> Any | None:
        accessor = getattr(guild, "get_channel", None)
        if callable(accessor):
            for candidate in (_maybe_snowflake(channel_id), channel_id):
                try:
                    channel = accessor(candidate)
                except TypeError:
                    continue
                if channel is not None:
                    return channel
        channels = getattr(guild, "channels", None)
        if channels is None:
            channels = getattr(guild, "voice_channels", None)
        if channels is None:
            return None
        for channel in channels:
            if _clean(getattr(channel, "id", "")) == channel_id:
                return channel
        return None

    def _iter_channels(self, guild: Any) -> list[Any]:
        channels = getattr(guild, "channels", None)
        if channels is None:
            channels = getattr(guild, "voice_channels", None)
        if channels is None:
            return []
        return list(channels)

    def _iter_voice_states(self, guild: Any) -> list[Any]:
        voice_states = getattr(guild, "voice_states", None)
        if voice_states is None:
            return []
        if isinstance(voice_states, dict):
            return list(voice_states.values())
        if isinstance(voice_states, (list, tuple, set)):
            return list(voice_states)
        if hasattr(voice_states, "values"):
            try:
                return list(voice_states.values())
            except TypeError:
                pass
        return list(voice_states)

    @staticmethod
    def _voice_state_channel_id(voice_state: Any) -> str:
        channel_id = _clean(getattr(voice_state, "channel_id", ""))
        if channel_id:
            return channel_id
        channel = getattr(voice_state, "channel", None)
        if channel is not None:
            return _clean(getattr(channel, "id", ""))
        return ""

    @staticmethod
    def _voice_state_user_id(voice_state: Any) -> str:
        user_id = _clean(getattr(voice_state, "user_id", ""))
        if user_id:
            return user_id
        member = getattr(voice_state, "member", None)
        if member is not None:
            return _clean(getattr(member, "id", ""))
        return ""

    async def _guild_member(self, guild_id: str, user_id: str, ctx: Any | None) -> Any | None:
        mover = self._mover
        if mover is None:
            return None
        member = mover.guild_member(guild_id, user_id, ctx=ctx) if self._accepts_keyword(mover.guild_member, "ctx") else mover.guild_member(guild_id, user_id)
        return await _await_maybe(member)

    async def _guild_member_move(self, guild_id: str, user_id: str, channel_id: str, ctx: Any | None) -> Any | None:
        mover = self._mover
        if mover is None:
            return None
        method = mover.guild_member_move
        if self._accepts_keyword(method, "ctx"):
            result = method(guild_id, user_id, channel_id, ctx=ctx)
        else:
            result = method(guild_id, user_id, channel_id)
        return await _await_maybe(result)

    async def _user_channel_permissions(self, user_id: str, channel_id: str, ctx: Any | None) -> int:
        mover = self._mover
        if mover is None:
            raise RuntimeError("shuffle service is unavailable")
        method = mover.user_channel_permissions
        if self._accepts_keyword(method, "ctx"):
            result = method(user_id, channel_id, ctx=ctx)
        else:
            result = method(user_id, channel_id)
        value = await _await_maybe(result)
        return int(value or 0)

    @staticmethod
    def _accepts_keyword(func: Any, keyword: str) -> bool:
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return False
        return keyword in signature.parameters

    def _shuffle_strings(self, values: list[str]) -> None:
        if len(values) < 2:
            return
        self._rng.shuffle(values)


async def _await_maybe(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
