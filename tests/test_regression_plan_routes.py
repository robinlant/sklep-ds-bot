from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from voice_tracker.commands import (
    AUDIT_COMMAND_NAME,
    AUTOROLE_COMMAND_NAME,
    INSPECT_ACTIVE_ALL_COMMAND,
    INSPECT_COMMAND_NAME,
    INSPECT_HISTORY_ALL_COMMAND,
    Service,
    can_use_voice_command,
    option_channel_id,
    option_role_id,
    option_user_id,
    resolve_command_channel,
)
from voice_tracker.discord_models import (
    ApplicationCommandInteractionData,
    ApplicationCommandInteractionDataOption,
    ApplicationCommandInteractionDataResolved,
    CHANNEL_TYPE_GUILD_STAGE_VOICE,
    CHANNEL_TYPE_GUILD_VOICE,
    Channel,
    INTERACTION_APPLICATION_COMMAND,
    Interaction,
    InteractionCreate,
    Member,
    PERMISSION_ADMINISTRATOR,
    PERMISSION_MANAGE_GUILD,
    User,
)


class _FakeDispatchSession:
    def __init__(self) -> None:
        self.handlers: list[Callable[[Any, InteractionCreate], None]] = []
        self.responses: list[Any] = []

    def add_handler(self, handler: Callable[[Any, InteractionCreate], None]) -> None:
        self.handlers.append(handler)

    def interaction_respond(self, _interaction: Interaction, response: Any) -> None:
        self.responses.append(response)


def _inspect_interaction(*, permissions: int, channel_option_value: str | int = "c1") -> InteractionCreate:
    channel_id = str(channel_option_value)
    return InteractionCreate(
        interaction=Interaction(
            type=INTERACTION_APPLICATION_COMMAND,
            guild_id="g1",
            channel_id="t1",
            member=Member(user=User(id="u1"), permissions=permissions),
            data=ApplicationCommandInteractionData(
                name=INSPECT_COMMAND_NAME,
                options=[ApplicationCommandInteractionDataOption(name="channel", type="channel", value=channel_option_value)],
                resolved=ApplicationCommandInteractionDataResolved(
                    channels={
                        channel_id: Channel(
                            id=channel_id,
                            guild_id="g1",
                            type=CHANNEL_TYPE_GUILD_VOICE,
                        )
                    }
                ),
            ),
        )
    )


def test_inspect_top_level_channel_option_routes_without_empty_command_failure() -> None:
    session = _FakeDispatchSession()
    service = Service()
    handler = service.install(session, allowed_guild_id="g1", bot_admin_user_ids=[])

    handler(session, _inspect_interaction(permissions=PERMISSION_ADMINISTRATOR))

    assert len(session.responses) == 1
    description = session.responses[0].data.embeds[0].description
    assert description == "No active session in that channel."


@pytest.mark.parametrize(
    ("root", "command"),
    [
        (AUDIT_COMMAND_NAME, "channel"),
        (INSPECT_COMMAND_NAME, "channel"),
        (INSPECT_COMMAND_NAME, INSPECT_ACTIVE_ALL_COMMAND),
        (INSPECT_COMMAND_NAME, INSPECT_HISTORY_ALL_COMMAND),
        (AUTOROLE_COMMAND_NAME, "role"),
    ],
)
def test_admin_only_routes_deny_non_admin_and_allow_administrator(root: str, command: str) -> None:
    plain_user = InteractionCreate(interaction=Interaction(member=Member(user=User(id="u-plain"), permissions=0)))
    guild_manager = InteractionCreate(interaction=Interaction(member=Member(user=User(id="u-manage"), permissions=PERMISSION_MANAGE_GUILD)))
    allowlisted_non_admin = InteractionCreate(interaction=Interaction(member=Member(user=User(id="u-allowlisted"), permissions=0)))
    administrator = InteractionCreate(interaction=Interaction(member=Member(user=User(id="u-admin"), permissions=PERMISSION_ADMINISTRATOR)))

    assert can_use_voice_command(plain_user, [], root, command) is False
    assert can_use_voice_command(guild_manager, [], root, command) is False
    assert can_use_voice_command(allowlisted_non_admin, ["u-allowlisted"], root, command) is False
    assert can_use_voice_command(administrator, [], root, command) is True


@pytest.mark.parametrize(
    ("resolver", "option_name"),
    [
        (option_channel_id, "channel"),
        (option_user_id, "user"),
        (option_role_id, "role"),
    ],
)
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("669151106814967819", "669151106814967819"),
        (" 669151106814967819 ", "669151106814967819"),
        (669151106814967819, "669151106814967819"),
    ],
)
def test_snowflake_option_helpers_accept_string_and_integer_values(
    resolver: Callable[[list[ApplicationCommandInteractionDataOption], str], str],
    option_name: str,
    value: str | int,
    expected: str,
) -> None:
    options = [ApplicationCommandInteractionDataOption(name=option_name, value=value)]

    assert resolver(options, option_name) == expected


def test_resolve_command_channel_accepts_integer_snowflake_option_value() -> None:
    interaction = _inspect_interaction(
        permissions=PERMISSION_ADMINISTRATOR,
        channel_option_value=669151106814967819,
    )

    resolved = resolve_command_channel(
        interaction,
        interaction.application_command_data().options,
        "channel",
        CHANNEL_TYPE_GUILD_VOICE,
        CHANNEL_TYPE_GUILD_STAGE_VOICE,
    )

    assert resolved == "669151106814967819"
