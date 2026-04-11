from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import discord
from nats.aio.client import Client as NATS
from pymongo import MongoClient

from voice_tracker.bus import Bus
from voice_tracker import domain
from voice_tracker.gateway import Service as GatewayService, summary_from_payload
from voice_tracker.repository import Repository
from voice_tracker.runtime import load_config, require_event_signing_secret


SUMMARY_EMBED_COLOR = 0x5865F2


async def _resolve_channel(client: discord.Client, channel_id: str):
    snowflake = int(channel_id)
    channel = client.get_channel(snowflake)
    if channel is None:
        channel = await client.fetch_channel(snowflake)
    return channel


async def _send_summary(client: discord.Client, channel_id: str, message: str) -> None:
    channel = await _resolve_channel(client, channel_id)
    embed = discord.Embed(title="Voice Session Summary", description=message, color=SUMMARY_EMBED_COLOR)
    embed.set_footer(text="Voice Tracker")
    await channel.send(embed=embed)


async def _deliver_pending(client: discord.Client, repo: Repository) -> None:
    for session in repo.list_summaries_pending_delivery(None):
        if not session.summary_channel_id or not session.summary_message:
            continue
        claimed = repo.claim_session_summary_delivery(None, session.id, datetime.now(UTC))
        if not claimed:
            continue
        try:
            await _send_summary(client, session.summary_channel_id, session.summary_message)
        except Exception:
            repo.release_session_summary_delivery_claim(None, session.id)
            continue
        repo.mark_session_summary_delivered(None, session.id, datetime.now(UTC))


async def main() -> None:
    cfg = load_config()
    if cfg.discord_token == "":
        raise SystemExit("DISCORD_TOKEN is required")
    require_event_signing_secret(cfg.event_signing_secret)

    mongo_client = MongoClient(cfg.mongo_uri)
    repo = Repository(mongo_client[cfg.mongo_db])

    nats = NATS()
    await nats.connect(cfg.nats_url)
    bus = Bus(nats, cfg.event_signing_secret, "gateway")

    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    intents.members = True
    client = discord.Client(intents=intents)
    GatewayService(client, bus).install()

    async def handle_summary(payload: bytes) -> None:
        event = summary_from_payload(payload)
        if event.channel_id == "" or event.message == "":
            return
        session = repo.get_session_by_id(None, event.session_id)
        if (
            session is None
            or session.guild_id != event.guild_id
            or session.summary_channel_id != event.channel_id
            or session.summary_message != event.message
        ):
            return
        claimed = repo.claim_session_summary_delivery(None, event.session_id, datetime.now(UTC))
        if not claimed:
            return
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                await _send_summary(client, event.channel_id, event.message)
            except Exception as exc:
                last_error = exc
                await asyncio.sleep((attempt + 1) * 0.25)
                continue
            repo.mark_session_summary_delivered(None, event.session_id, datetime.now(UTC))
            return
        repo.release_session_summary_delivery_claim(None, event.session_id)
        if last_error is not None:
            raise last_error

    await bus.subscribe(None, domain.SUBJECT_SUMMARY_READY, repo, handle_summary)

    await client.login(cfg.discord_token)
    await _deliver_pending(client, repo)

    async def sweep_pending() -> None:
        while True:
            await asyncio.sleep(60)
            await _deliver_pending(client, repo)

    sweep = asyncio.create_task(sweep_pending())
    try:
        await client.connect()
    finally:
        sweep.cancel()
        await bus.aclose()
        mongo_client.close()


if __name__ == "__main__":
    asyncio.run(main())
