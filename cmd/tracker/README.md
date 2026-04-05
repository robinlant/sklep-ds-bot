# Tracker Service

Owns voice-session state and participant timing.

## What It Does

- Consumes `voice.events`.
- Creates a session on the first tracked join.
- Tracks participant intervals and total time.
- Closes the session when the channel becomes empty.

## How To Use

- Run locally with `go run ./cmd/tracker`.
- In Docker Compose, this is the `tracker` service.
- Requires MongoDB, NATS, and the event signing secret.

## How It Fits

- Input: voice-state events from NATS.
- Output: session and participant documents in MongoDB, plus `session.closed`.
- Depends on: `internal/tracker`, `internal/mongo`, `internal/bus`, and shared domain types.

## AI Notes

- This is the owner of voice-session lifecycle rules.
- Keep session timing logic here, not in the gateway or writer.
- If you add more voice features later, extend this service or add a sibling service, but keep the session model stable.
