# Commands Service

Owns guild settings commands for the bot.

## What It Does

- Registers and handles Discord slash commands.
- Stores guild settings in MongoDB.
- Controls which channels are tracked and where summaries are posted.

## How To Use

- Run locally with `go run ./cmd/commands`.
- In Docker Compose, this is the `commands` service.
- Requires Discord token, application ID, guild ID, MongoDB, and the event signing secret.

## Commands

- `voice-track-mode`: set `all`, `none`, or `specific`.
- `voice-track-channels`: set tracked voice channels.
- `voice-summary-channel`: set the recap destination.
- `voice-settings`: inspect current settings.

## How It Fits

- Input: Discord interactions.
- Output: guild settings in MongoDB.
- Depends on: `internal/commands`, `internal/mongo`, `internal/config`, and Discord permissions.

## AI Notes

- This is the control plane for per-guild configuration.
- Keep permission checks here.
- Add future admin commands here before exposing any external API.
