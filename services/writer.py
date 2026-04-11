from __future__ import annotations

import asyncio

from nats.aio.client import Client as NATS
from pymongo import MongoClient

from voice_tracker.bus import Bus
from voice_tracker import domain
from voice_tracker.repository import Repository
from voice_tracker.runtime import load_config, require_event_signing_secret
from voice_tracker.summary import Service


async def main() -> None:
    cfg = load_config()
    require_event_signing_secret(cfg.event_signing_secret)

    mongo_client = MongoClient(cfg.mongo_uri)
    repo = Repository(mongo_client[cfg.mongo_db])
    repo.ensure_indexes(None)

    nats = NATS()
    await nats.connect(cfg.nats_url)
    bus = Bus(nats, cfg.event_signing_secret, "writer")
    service = Service(repo, bus)

    await bus.subscribe(None, domain.SUBJECT_SESSION_CLOSED, repo, service.HandleSessionClosed)
    await service.Start()

    async def sweep_pending() -> None:
        while True:
            await asyncio.sleep(60)
            await service.Start()

    sweep = asyncio.create_task(sweep_pending())
    try:
        await asyncio.Event().wait()
    finally:
        sweep.cancel()
        await bus.aclose()
        mongo_client.close()


if __name__ == "__main__":
    asyncio.run(main())
