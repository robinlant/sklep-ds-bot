from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import discord

from voice_tracker.appcommands import commands
from voice_tracker.discord_models import (
    ApplicationCommandInteractionData,
    ApplicationCommandInteractionDataOption,
    ApplicationCommandInteractionDataResolved,
    Channel,
    Interaction,
    InteractionCreate,
    Member,
    User,
)
from voice_tracker.runtime import load_config, register_commands_http
from voice_tracker.shuffle import (
    Service as ShuffleService,
    can_use_shuffle_command,
    handle_equal_command,
    handle_gather_command,
    parse_shuffle_route,
)


logger = logging.getLogger(__name__)


def _build_client(token: str) -> discord.Client:
    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    intents.members = True
    return discord.Client(intents=intents)


async def main() -> None:
    cfg = load_config()
    if cfg.discord_token == "":
        raise SystemExit("DISCORD_TOKEN is required")
    if cfg.discord_application_id == "":
        raise SystemExit("DISCORD_APPLICATION_ID is required")
    if cfg.discord_guild_id == "":
        raise SystemExit("DISCORD_GUILD_ID is required")
    print(f"shuffle service starting guild={cfg.discord_guild_id}")

    client = _build_client(cfg.discord_token)
    ready: asyncio.Queue[str] = asyncio.Queue(maxsize=1)

    @client.event
    async def on_ready() -> None:
        if client.user is not None:
            await ready.put(str(client.user.id))

    @client.event
    async def on_interaction(interaction: discord.Interaction) -> None:
        data = getattr(interaction, "data", None)
        if not isinstance(data, dict) or data.get("name") != "shuffle":
            return
        if str(getattr(interaction, "guild_id", "") or "") != cfg.discord_guild_id:
            return
        await interaction.response.defer(ephemeral=True)
        model = _interaction_model(interaction)
        group, command, options = parse_shuffle_route(model.application_command_data().options)
        service = ShuffleService(DiscordState(client), DiscordMover(client), str(client.user.id if client.user else ""))
        try:
            if group not in {"equal", "gather"}:
                content = "Unknown shuffle command."
            elif not can_use_shuffle_command(model, cfg.bot_admin_user_ids):
                content = "Insufficient permissions."
            elif group == "equal":
                content = await handle_equal_command(service, model, command, options)
            elif group == "gather":
                content = await handle_gather_command(service, model, command, options)
        except ValueError as exc:
            content = str(exc)
        except Exception as exc:
            logger.exception("shuffle command failed")
            content = "Command failed. Check service logs."
        if content == "":
            content = "Done."
        await interaction.followup.send(content, ephemeral=True)

    await client.login(cfg.discord_token)
    connect_task = asyncio.create_task(client.connect())
    try:
        try:
            bot_user_id = await asyncio.wait_for(ready.get(), timeout=30.0)
        except asyncio.TimeoutError as exc:
            raise SystemExit("timeout waiting for discord ready event") from exc
        if bot_user_id == "":
            raise SystemExit("discord ready event missing bot user id")
        print(f"shuffle service ready guild={cfg.discord_guild_id}")
        await register_commands_http(cfg.discord_token, cfg.discord_application_id, cfg.discord_guild_id, commands())
        print(f"shuffle commands registered count={len(commands())} guild={cfg.discord_guild_id}")
        await connect_task
    finally:
        connect_task.cancel()
        await client.close()


class DiscordState:
    def __init__(self, client: discord.Client) -> None:
        self.client = client

    def get_guild(self, guild_id: object) -> "GuildView | None":
        guild = self.client.get_guild(int(guild_id))
        return None if guild is None else GuildView(guild)


class GuildView:
    def __init__(self, guild: discord.Guild) -> None:
        self.guild = guild
        self.id = str(guild.id)
        self.channels = list(guild.channels)
        self.members = list(guild.members)

    def get_channel(self, channel_id: object):
        return self.guild.get_channel(int(channel_id))

    def get_member(self, user_id: object):
        return self.guild.get_member(int(user_id))

    @property
    def voice_states(self) -> list[SimpleNamespace]:
        states: list[SimpleNamespace] = []
        for channel in self.guild.voice_channels:
            for member in channel.members:
                states.append(SimpleNamespace(user_id=str(member.id), channel_id=str(channel.id), member=member))
        for channel in self.guild.stage_channels:
            for member in channel.members:
                states.append(SimpleNamespace(user_id=str(member.id), channel_id=str(channel.id), member=member))
        return states


class DiscordMover:
    def __init__(self, client: discord.Client) -> None:
        self.client = client

    async def guild_member(self, guild_id: str, user_id: str, *args, **kwargs):
        guild = self.client.get_guild(int(guild_id))
        if guild is None:
            raise RuntimeError("guild state is unavailable")
        return guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))

    async def guild_member_move(self, guild_id: str, user_id: str, channel_id: str | None, *args, **kwargs) -> None:
        if channel_id is None:
            raise ValueError("channel id is required")
        guild = self.client.get_guild(int(guild_id))
        if guild is None:
            raise RuntimeError("guild state is unavailable")
        member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            raise ValueError(f"unable to resolve channel {channel_id}")
        await member.move_to(channel)

    async def user_channel_permissions(self, user_id: str, channel_id: str, *args, **kwargs) -> int:
        for guild in self.client.guilds:
            channel = guild.get_channel(int(channel_id))
            if channel is None:
                continue
            member = guild.get_member(int(user_id))
            if member is None:
                member = guild.me
            if member is None:
                return 0
            return channel.permissions_for(member).value
        return 0


def _interaction_model(interaction: discord.Interaction) -> InteractionCreate:
    data = getattr(interaction, "data", {}) or {}
    guild_id = str(getattr(interaction, "guild_id", "") or "")
    permissions = getattr(getattr(interaction, "permissions", None), "value", 0) or 0
    user = getattr(interaction, "user", None)
    user_id = str(getattr(user, "id", "") or "")
    return InteractionCreate(
        interaction=Interaction(
            type="application_command",
            guild_id=guild_id,
            member=Member(user=User(id=user_id), permissions=permissions),
            user=User(id=user_id),
            data=ApplicationCommandInteractionData(
                name=str(data.get("name", "")),
                options=_options(data.get("options", [])),
                resolved=ApplicationCommandInteractionDataResolved(channels=_channels(data.get("resolved", {}).get("channels", {}))),
            ),
        )
    )


def _options(raw_options: list[dict]) -> list[ApplicationCommandInteractionDataOption]:
    return [
        ApplicationCommandInteractionDataOption(
            name=str(option.get("name", "")),
            value=option.get("value"),
            type=str(option.get("type", "")),
            options=_options(option.get("options", [])),
        )
        for option in raw_options or []
    ]


def _channels(raw_channels: dict) -> dict[str, Channel]:
    return {
        str(channel_id): Channel(
            id=str(channel_id),
            guild_id=str(channel.get("guild_id", "") or channel.get("guildId", "")),
            type=_channel_type(channel.get("type")),
        )
        for channel_id, channel in (raw_channels or {}).items()
    }


def _channel_type(value: object) -> str:
    return {0: "guild_text", 2: "guild_voice", 13: "guild_stage_voice"}.get(value, str(value))


if __name__ == "__main__":
    asyncio.run(main())
