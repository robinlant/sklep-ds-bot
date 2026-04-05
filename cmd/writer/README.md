# Writer Service

Builds the final recap for a closed voice session.

## What It Does

- Consumes `session.closed`.
- Reads the session and participant history from MongoDB.
- Builds the final summary text.
- Publishes `session.summary`.

## How To Use

- Run locally with `go run ./cmd/writer`.
- In Docker Compose, this is the `writer` service.
- Requires MongoDB, NATS, and the event signing secret.

## How It Fits

- Input: closed session events from NATS.
- Output: formatted recap events to NATS.
- Depends on: `internal/summary`, `internal/mongo`, `internal/bus`, and shared domain types.

## AI Notes

- Keep recap formatting isolated here.
- Do not query Discord from this service.
- If summary shape changes, update the shared domain types and the gateway consumer together.
