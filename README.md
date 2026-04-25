# Voice Tracker

Discord voice-session tracker built as Python microservices with MongoDB and NATS.

Last updated: April 25, 2026.

## What Changed

Recent production stabilization changes include:

- Added canonical `/settings` command and kept legacy aliases (`/audit`, `/bot-setting`) with guidance text.
- Deprecated `/track` and `/track-list` as no-op commands (tracking is now operationally treated as all-channel).
- Fixed `/inspect` routing/permission edge cases for top-level options.
- Improved `/userinfo` output formatting and voice-total sourcing.
- Added repository read models for dashboard and user profile totals.
- Hardened tracker leave/close fallback behavior when runtime state is missing.
- Added startup retry/backoff in writer service and expanded CI test lanes.

## Services

- `services.gateway`: consumes Discord voice-state updates and publishes `voice.events`; delivers session summaries back to Discord.
- `services.tracker`: owns session/participant lifecycle and emits `session.closed`.
- `services.writer`: consumes `session.closed`, builds summary text, emits `session.summary`.
- `services.commands`: owns slash command registration and command execution.

Shared package code is in `voice_tracker/`.

## Event Flow

1. Gateway receives Discord voice-state updates.
2. Gateway publishes `voice.events` to NATS.
3. Tracker updates sessions/participants in MongoDB.
4. Tracker emits `session.closed` when a tracked channel session ends.
5. Writer generates summary payload and emits `session.summary`.
6. Gateway receives `session.summary` and posts it to the configured output channel.

## Command Docs

Full command reference lives in [COMMANDS.md](COMMANDS.md).

## Runtime Dependencies

- Python 3.11+
- MongoDB
- NATS
- Discord bot token + app/guild IDs

## Configuration

Use `.env.example` as baseline.

Important variables:

- `DISCORD_TOKEN`
- `DISCORD_APPLICATION_ID`
- `DISCORD_GUILD_ID`
- `MONGO_URI`, `MONGO_DB`
- `NATS_URL`
- `EVENT_SIGNING_SECRET`
- `TRACKING_MODE` (recommended: `all`)
- `TRACKED_CHANNEL_IDS` (startup default only)

`BOT_ADMIN_USER_IDS` remains for compatibility but is not the primary admin policy path.

## Local Development

```bash
python -m pip install -e ".[test]"
pytest -q
```

## Docker Compose

```bash
docker compose up --build
```

See [EXAMPLES.md](EXAMPLES.md) for sample environment and compose usage.

## CI

`CI` workflow currently runs:

- fast lanes: Python 3.11 and 3.12
- forward canary: Python 3.14 (non-blocking)
- deprecation-strict lane: `pytest -W error::DeprecationWarning` (non-blocking)

## Documentation Map

- [README.md](README.md): project overview and setup
- [COMMANDS.md](COMMANDS.md): slash command catalog and behavior
- [EXAMPLES.md](EXAMPLES.md): compose and env examples
- [AGENTS_README.md](AGENTS_README.md): maintainer notes for agent-driven updates
- `docs/`: historical research and migration notes
