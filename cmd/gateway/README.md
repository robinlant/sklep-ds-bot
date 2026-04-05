# Gateway Service

Consumes Discord events and bridges them to the rest of the system.

## What It Does

- Connects to Discord.
- Converts voice-state updates into `voice.events`.
- Consumes `session.summary` and posts recap messages to Discord.

## How To Use

- Run locally with `go run ./cmd/gateway`.
- In Docker Compose, this is the `gateway` service.
- Requires Discord token, MongoDB, NATS, and the event signing secret.

## How It Fits

- Input: Discord voice updates and summary events from NATS.
- Output: `voice.events` and Discord recap messages.
- Depends on: `internal/gateway`, `internal/bus`, and shared config/domain types.

## AI Notes

- Keep this service stateless except for Discord connection state.
- Do not add business rules here; it should only bridge Discord and the event bus.
- Summary delivery should stay small and observable.
