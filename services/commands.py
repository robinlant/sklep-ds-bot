from __future__ import annotations

import asyncio
import logging

import discord
from pymongo import MongoClient

from voice_tracker.appcommands import commands
from voice_tracker.commands import Service as VoiceService, can_use_voice_command, parse_voice_route
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
from voice_tracker.repository import Repository
from voice_tracker.runtime import load_config, register_commands_http


logger = logging.getLogger(__name__)


def _build_client(token: str) -> discord.Client:
    intents = discord.Intents.none()
    intents.guilds = True
    return discord.Client(intents=intents)


async def main() -> None:
    cfg = load_config()
    if cfg.discord_token == "":
        raise SystemExit("DISCORD_TOKEN is required")
    if cfg.discord_application_id == "":
        raise SystemExit("DISCORD_APPLICATION_ID is required")
    if cfg.discord_guild_id == "":
        raise SystemExit("DISCORD_GUILD_ID is required")

    print(f"commands service starting guild={cfg.discord_guild_id}")
    mongo_client = MongoClient(cfg.mongo_uri)
    repo = Repository(mongo_client[cfg.mongo_db])
    repo.ensure_indexes(None)
    service = VoiceService(repo)

    client = _build_client(cfg.discord_token)

    @client.event
    async def on_interaction(interaction: discord.Interaction) -> None:
        data = getattr(interaction, "data", None)
        if not isinstance(data, dict) or data.get("name") != "voice":
            return
        if str(getattr(interaction, "guild_id", "") or "") != cfg.discord_guild_id:
            return
        model = _interaction_model(interaction)
        group, command, options = parse_voice_route(model.application_command_data().options)
        if not can_use_voice_command(model, cfg.bot_admin_user_ids, group, command):
            content = "Insufficient permissions."
        else:
            try:
                content = service.handle_voice_command(None, model, group, command, options)
            except ValueError as exc:
                content = str(exc)
            except Exception as exc:
                logger.exception("voice command failed")
                content = "Command failed. Check service logs."
        if content == "":
            content = "Done."
        embed = discord.Embed(title="Voice Tracker", description=content, color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    await client.login(cfg.discord_token)
    try:
        await register_commands_http(cfg.discord_token, cfg.discord_application_id, cfg.discord_guild_id, commands())
        print(f"application commands registered count={len(commands())} guild={cfg.discord_guild_id}")
        await client.connect()
    finally:
        await client.close()
        mongo_client.close()


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
