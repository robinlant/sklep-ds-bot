# Bus Package

Shared NATS wrapper for publishing and subscribing to signed events.

## What It Does

- Connects to NATS.
- Publishes JSON payloads wrapped in a signed envelope.
- Subscribes to subjects and verifies envelope subject, issuer, signature, and freshness.
- Claims message IDs through the repository-backed dedupe path when one is provided.

## How To Use

- Services call `bus.Connect(...)` with the NATS URL, event secret, and issuer name.
- Publish with `PublishJSON`.
- Subscribe with `Subscribe(ctx, subject, deduper, handler)`.

## How It Fits

- This is the transport boundary between services.
- `gateway`, `tracker`, and `writer` all use it.
- It keeps event flow consistent, but it does not own business logic.

## AI Notes

- Treat this package as the message envelope layer.
- Do not put feature logic here.
- If a new event is added, update the shared subject map and the consuming service docs together.
