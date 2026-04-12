from __future__ import annotations

import asyncio

from nats.aio.client import Client as NATS
from pymongo import MongoClient

from voice_tracker.bus import Bus
from voice_tracker import domain
from voice_tracker.repository import Repository
from voice_tracker.runtime import load_config, require_event_signing_secret
from voice_tracker.tracker import Defaults, Service, decode_voice_event


async def main() -> None:
    cfg = load_config()
    require_event_signing_secret(cfg.event_signing_secret)

    mongo_client = MongoClient(cfg.mongo_uri)
    repo = Repository(mongo_client[cfg.mongo_db])
    repo.ensure_indexes(None)

    nats = NATS()
    await nats.connect(cfg.nats_url)
    bus = Bus(nats, cfg.event_signing_secret, "tracker")
    service = Service(
        repo,
        bus,
        Defaults(tracking_mode=cfg.tracking_mode, tracked_channel_ids=cfg.tracked_channel_ids),
    )

    async def handle(payload: bytes) -> None:
        await service.HandleVoiceEvent(decode_voice_event(payload))

    await bus.subscribe(None, domain.SUBJECT_VOICE_EVENT, repo, handle)
    await service.Start()

    try:
        await asyncio.Event().wait()
    finally:
        await bus.aclose()
        mongo_client.close()


if __name__ == "__main__":
    asyncio.run(main())
