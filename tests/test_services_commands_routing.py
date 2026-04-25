from __future__ import annotations

import pytest

from services import commands as commands_service
from voice_tracker.discord_models import (
    ApplicationCommandInteractionDataOption,
    Interaction,
    InteractionCreate,
    Member,
    PERMISSION_ADMINISTRATOR,
    User,
)


class _InspectServiceStub:
    def __init__(self) -> None:
        self.inspect_calls: list[tuple[str, list[ApplicationCommandInteractionDataOption]]] = []

    def handle_inspect_command(self, _ctx, _model, command: str, options: list[ApplicationCommandInteractionDataOption]) -> str:
        self.inspect_calls.append((command, options))
        return "inspect-ok"

    def remember_fallback_summary_channel(self, _ctx, _guild_id: str, _channel_id: str) -> None:
        raise AssertionError("legacy fallback should not be used for /inspect channel")

    def handle_voice_command(self, _ctx, _model, _root: str, _command: str, _options) -> str:
        raise AssertionError("legacy voice command handler should not be used for /inspect channel")


def _interaction_model(permissions: int) -> InteractionCreate:
    return InteractionCreate(
        interaction=Interaction(
            type="application_command",
            guild_id="g1",
            channel_id="c1",
            member=Member(user=User(id="u1"), permissions=permissions),
            user=User(id="u1"),
        )
    )


@pytest.mark.asyncio
async def test_dispatch_command_routes_top_level_inspect_channel_for_admin() -> None:
    service = _InspectServiceStub()
    result = await commands_service._dispatch_command(
        object(),
        service,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        _interaction_model(PERMISSION_ADMINISTRATOR),
        "inspect",
        "",
        [ApplicationCommandInteractionDataOption(name="channel", value=123456789012345678)],
        [],
    )

    assert result == "inspect-ok"
    assert len(service.inspect_calls) == 1
    command, options = service.inspect_calls[0]
    assert command == "active.channel"
    assert options[0].value == "123456789012345678"


@pytest.mark.asyncio
async def test_dispatch_command_rejects_top_level_inspect_channel_without_admin() -> None:
    service = _InspectServiceStub()
    result = await commands_service._dispatch_command(
        object(),
        service,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        _interaction_model(0),
        "inspect",
        "",
        [ApplicationCommandInteractionDataOption(name="channel", value=123456789012345678)],
        [],
    )

    assert result == "Insufficient permissions."
    assert service.inspect_calls == []


def test_normalize_snowflake_options_casts_int_channel_user_role_values() -> None:
    normalized = commands_service._normalize_snowflake_options(
        [
            ApplicationCommandInteractionDataOption(name="channel", value=101),
            ApplicationCommandInteractionDataOption(name="role", value=202),
            ApplicationCommandInteractionDataOption(name="user", value=303),
            ApplicationCommandInteractionDataOption(name="limit", value=5),
            ApplicationCommandInteractionDataOption(
                name="add",
                options=[ApplicationCommandInteractionDataOption(name="user", value=404)],
            ),
        ]
    )

    assert normalized[0].value == "101"
    assert normalized[1].value == "202"
    assert normalized[2].value == "303"
    assert normalized[3].value == 5
    assert normalized[4].options[0].value == "404"
