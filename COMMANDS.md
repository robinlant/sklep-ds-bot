# Command README

Slash command reference for the current production command surface.

Last updated: April 25, 2026.

## Access Model

- `ADMIN_ONLY`: requires Discord `Administrator` at runtime.
- `ALL_USER`: no admin requirement, but command-specific validation still applies.

## Command Catalog

### ADMIN_ONLY

- `/settings show`
  - Show current bot settings.
- `/settings mode mode:all`
  - Tracking mode endpoint. Only `all` is supported.
- `/settings summary-set channel:<text>`
  - Set summary/output channel.
- `/settings summary-clear`
  - Clear configured summary channel (fallback behavior applies).

- `/audit channel:<text>`
  - Legacy alias for settings summary channel update.
  - Shows deprecation guidance toward `/settings summary-set`.

- `/bot-setting`
  - Legacy alias for settings display.
  - Shows deprecation guidance toward `/settings show`.

- `/inspect channel:<voice|stage>`
  - Show active session details for one channel.

- `/autorole role:<role>`
  - Configure autorole (runtime safety checks enforce assignable/safe role).

- `/unmute add user:<member>`
  - Add member to auto-unmute list.
- `/unmute remove user:<member>`
  - Remove member from auto-unmute list.
- `/unmute list`
  - Show auto-unmute list.

- `/track add`
- `/track remove`
- `/track list`
- `/track-list clear`
  - Deprecated no-op commands kept for compatibility.
  - Bot responds with deprecation message; no per-channel tracking mutations are performed.

### ALL_USER

- `/jump channel:<voice|stage>`
  - Move invoking user to target channel if visibility/permission checks pass.

- `/dashboard`
  - Show top voice-time leaderboard from repository aggregates.

- `/userinfo user:<member>`
  - Show member profile summary and total voice time.

## Notes

- Command registration owner is `services.commands`.
- Runtime policy enforcement exists in command handlers; Discord UI visibility alone is not treated as authorization.
- `/inspect` supports additional internal route forms for compatibility/tests, but only the public route above is registered.
