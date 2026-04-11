from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

import pytest

from voice_tracker.shuffle import (
    CHANNEL_TYPE_GUILD_STAGE_VOICE,
    CHANNEL_TYPE_GUILD_VOICE,
    PERMISSION_ADMINISTRATOR,
    PERMISSION_MANAGE_GUILD,
    PERMISSION_VOICE_CONNECT,
    PERMISSION_VOICE_MOVE_MEMBERS,
    PERMISSION_VIEW_CHANNEL,
    ApplicationCommand,
    Result,
    Service,
    can_use_shuffle_command,
    format_gather_result,
    parse_excluded_user_ids,
    shuffle_application_command,
)


@dataclass(slots=True)
class FakeUser:
    id: str
    bot: bool = False


@dataclass(slots=True)
class FakeMember:
    guild_id: str
    user: FakeUser
    permissions: int = 0


@dataclass(slots=True)
class FakeChannel:
    id: str
    guild_id: str
    type: object


@dataclass(slots=True)
class FakeVoiceState:
    guild_id: str
    user_id: str
    channel_id: str


@dataclass(slots=True)
class FakeGuild:
    id: str
    channels: list[FakeChannel] = field(default_factory=list)
    voice_states: list[FakeVoiceState] = field(default_factory=list)
    members: list[FakeMember] = field(default_factory=list)

    def get_channel(self, channel_id: object) -> FakeChannel | None:
        value = str(channel_id)
        for channel in self.channels:
            if channel.id == value:
                return channel
        return None

    def get_member(self, user_id: object) -> FakeMember | None:
        value = str(user_id)
        for member in self.members:
            if member.user.id == value:
                return member
        return None


@dataclass(slots=True)
class FakeState:
    guild: FakeGuild

    def get_guild(self, guild_id: object) -> FakeGuild | None:
        if str(guild_id) == self.guild.id:
            return self.guild
        return None


class FakeMover:
    def __init__(
        self,
        members: dict[str, FakeMember] | None = None,
        perms: dict[str, int] | None = None,
        move_err: dict[str, Exception] | None = None,
        *,
        async_members: bool = False,
        async_perms: bool = False,
        async_moves: bool = False,
    ) -> None:
        self.members = members or {}
        self.perms = perms or {}
        self.move_err = move_err or {}
        self.async_members = async_members
        self.async_perms = async_perms
        self.async_moves = async_moves
        self.moves: list[tuple[str, str]] = []

    def guild_member(self, _guild_id: str, user_id: str, *args, **kwargs):
        member = self.members.get(user_id)
        if member is None:
            raise LookupError("member not found")
        if self.async_members:
            async def _value() -> FakeMember:
                return member

            return _value()
        return member

    def guild_member_move(self, _guild_id: str, user_id: str, channel_id: str | None, *args, **kwargs):
        if user_id in self.move_err:
            raise self.move_err[user_id]
        if channel_id is None:
            raise ValueError("channel id is required")
        if self.async_moves:
            async def _value() -> None:
                self.moves.append((user_id, channel_id))

            return _value()
        self.moves.append((user_id, channel_id))

    def user_channel_permissions(self, _user_id: str, channel_id: str, *args, **kwargs):
        value = self.perms.get(channel_id, 0)
        if self.async_perms:
            async def _value() -> int:
                return value

            return _value()
        return value


def make_service(guild: FakeGuild, mover: FakeMover, bot_user_id: str = "bot") -> Service:
    return Service(FakeState(guild), mover, bot_user_id, Random(1))


def make_voice_guild(
    guild_id: str,
    channel_specs: list[tuple[str, object]],
    voice_specs: list[tuple[str, str]],
    members: list[tuple[str, bool]] | None = None,
) -> FakeGuild:
    channels = [FakeChannel(channel_id, guild_id, channel_type) for channel_id, channel_type in channel_specs]
    voice_states = [FakeVoiceState(guild_id, user_id, channel_id) for user_id, channel_id in voice_specs]
    member_objects = [
        FakeMember(guild_id, FakeUser(user_id, is_bot))
        for user_id, is_bot in (members or [])
    ]
    return FakeGuild(guild_id, channels=channels, voice_states=voice_states, members=member_objects)


def grant_full_voice_perms(mover: FakeMover, channel_ids: list[str]) -> None:
    value = PERMISSION_VIEW_CHANNEL | PERMISSION_VOICE_CONNECT | PERMISSION_VOICE_MOVE_MEMBERS
    for channel_id in channel_ids:
        mover.perms[channel_id] = value


@pytest.mark.asyncio
async def test_equal_balances_users_evenly() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE), ("c3", CHANNEL_TYPE_GUILD_VOICE)],
        [
            ("u1", "c1"),
            ("u2", "c1"),
            ("u3", "c1"),
            ("u4", "c2"),
            ("u5", "c2"),
            ("u6", "c3"),
            ("u7", "c3"),
        ],
        [(f"u{i}", False) for i in range(1, 8)],
    )
    mover = FakeMover()
    grant_full_voice_perms(mover, ["c1", "c2", "c3"])
    svc = make_service(guild, mover)

    result = await svc.equal(guild_id, ["c1", "c2", "c3"], None)

    assert result.failures == []
    assert result.movable_users == 7
    assert len(result.channel_results) == 3
    counts = {channel.channel_id: channel.moved for channel in result.channel_results}
    assert sum(counts.values()) == 7
    assert all(2 <= count <= 3 for count in counts.values())
    assert len(mover.moves) == 7
    assert len({user_id for user_id, _ in mover.moves}) == 7


@pytest.mark.asyncio
async def test_equal_supports_async_mover_methods() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE)],
        [("u1", "c1"), ("u2", "c2")],
        [("u1", False)],
    )
    mover = FakeMover(
        members={"u2": FakeMember(guild_id, FakeUser("u2"))},
        async_members=True,
        async_perms=True,
        async_moves=True,
    )
    grant_full_voice_perms(mover, ["c1", "c2"])
    svc = make_service(guild, mover)

    result = await svc.equal(guild_id, ["c1", "c2"], None)

    assert result.moved_users == 2
    assert len(mover.moves) == 2


@pytest.mark.asyncio
async def test_equal_errors_when_not_enough_people() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE), ("c3", CHANNEL_TYPE_GUILD_VOICE)],
        [("u1", "c1"), ("u2", "c2")],
        [("u1", False), ("u2", False)],
    )
    mover = FakeMover()
    grant_full_voice_perms(mover, ["c1", "c2", "c3"])
    svc = make_service(guild, mover)

    with pytest.raises(ValueError, match="not enough people"):
        await svc.equal(guild_id, ["c1", "c2", "c3"], None)

    assert mover.moves == []


@pytest.mark.asyncio
async def test_equal_respects_exclusions_and_bots() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE)],
        [("u1", "c1"), ("u2", "c1"), ("u3", "c2"), ("bot-user", "c2")],
        [("u1", False), ("u2", False), ("u3", False), ("bot-user", True)],
    )
    mover = FakeMover()
    grant_full_voice_perms(mover, ["c1", "c2"])
    svc = make_service(guild, mover, bot_user_id="bot")

    result = await svc.equal(guild_id, ["c1", "c2"], ["u2"])

    assert result.movable_users == 2
    assert result.excluded_users == 1
    assert len(mover.moves) == 2


@pytest.mark.asyncio
async def test_equal_rejects_duplicate_channels() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE)],
        [],
        [],
    )
    mover = FakeMover()
    grant_full_voice_perms(mover, ["c1", "c2"])
    svc = make_service(guild, mover)

    with pytest.raises(ValueError, match="duplicate channel c1"):
        await svc.equal(guild_id, ["c1", "c1"], None)

    assert mover.moves == []


@pytest.mark.asyncio
async def test_equal_keeps_shuffling_after_move_failure() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE)],
        [("u1", "c1"), ("u2", "c1"), ("u3", "c2")],
        [("u1", False), ("u2", False), ("u3", False)],
    )
    mover = FakeMover(move_err={"u2": RuntimeError("temporary move failure")})
    grant_full_voice_perms(mover, ["c1", "c2"])
    svc = make_service(guild, mover)

    result = await svc.equal(guild_id, ["c1", "c2"], None)

    assert result.moved_users == 2
    assert len(result.failures) == 1
    assert len(mover.moves) == 2


@pytest.mark.asyncio
async def test_gather_all_moves_everyone_into_one_channel() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE), ("c3", CHANNEL_TYPE_GUILD_STAGE_VOICE)],
        [("u1", "c1"), ("u2", "c1"), ("u3", "c2"), ("u4", "c3"), ("u5", "c3")],
        [(f"u{i}", False) for i in range(1, 6)],
    )
    mover = FakeMover()
    grant_full_voice_perms(mover, ["c1", "c2", "c3"])
    svc = make_service(guild, mover)

    result = await svc.gather(guild_id, "c2", None, None)

    assert result.movable_users == 4
    assert result.moved_users == 4
    assert len(result.channel_results) == 1
    assert result.channel_results[0].channel_id == "c2"
    assert result.channel_results[0].moved == 4
    assert len(mover.moves) == 4
    assert all(user_id != "u3" for user_id, _ in mover.moves)


@pytest.mark.asyncio
async def test_gather_all_skips_inaccessible_channels() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE), ("c3", CHANNEL_TYPE_GUILD_VOICE), ("c4", CHANNEL_TYPE_GUILD_VOICE)],
        [("u1", "c1"), ("u2", "c3"), ("u3", "c2")],
        [("u1", False), ("u2", False), ("u3", False)],
    )
    mover = FakeMover()
    grant_full_voice_perms(mover, ["c1", "c2", "c4"])
    svc = make_service(guild, mover)

    result = await svc.gather(guild_id, "c2", None, None)

    assert result.movable_users == 1
    assert result.skipped_channels == 1
    assert result.skipped_channel_ids == ["c3"]
    assert result.moved_users == 1
    assert len(mover.moves) == 1


@pytest.mark.asyncio
async def test_gather_select_uses_chosen_sources() -> None:
    guild_id = "g1"
    guild = make_voice_guild(
        guild_id,
        [("c1", CHANNEL_TYPE_GUILD_VOICE), ("c2", CHANNEL_TYPE_GUILD_VOICE), ("c3", CHANNEL_TYPE_GUILD_VOICE), ("c4", CHANNEL_TYPE_GUILD_VOICE)],
        [("u1", "c1"), ("u2", "c3"), ("u3", "c4")],
        [("u1", False), ("u2", False), ("u3", False)],
    )
    mover = FakeMover()
    grant_full_voice_perms(mover, ["c1", "c2", "c3", "c4"])
    svc = make_service(guild, mover)

    result = await svc.gather(guild_id, "c2", ["c1", "c3"], None)

    assert result.movable_users == 2
    assert len(mover.moves) == 2
    assert all(user_id != "u3" for user_id, _ in mover.moves)


def test_parse_excluded_user_ids() -> None:
    ids = parse_excluded_user_ids("<@123>, 456 <@!789> 456")
    assert ids == ["123", "456", "789"]
    with pytest.raises(ValueError, match="invalid excluded user"):
        parse_excluded_user_ids("abc")


def test_shuffle_application_command_shape() -> None:
    command = shuffle_application_command()
    assert isinstance(command, ApplicationCommand)
    assert command.name == "shuffle"
    assert len(command.options) == 2

    groups = {option.name: option for option in command.options}
    gather_group = groups["gather"]
    assert len(gather_group.options) == 2
    select_command = gather_group.options[1]
    assert select_command.name == "select"
    assert len(select_command.options) >= 3

    equal_group = groups["equal"]
    assert len(equal_group.options) == 3
    assert {option.name for option in equal_group.options} == {"two", "three", "four"}


def test_format_gather_result_includes_skipped_channels() -> None:
    content = format_gather_result("c2", Result(moved_users=3, skipped_channels=2, skipped_channel_ids=["c3", "c4"]))
    assert "Skipped 2 inaccessible channel(s): <#c3>, <#c4>." in content


def test_can_use_shuffle_command() -> None:
    manage = type("Interaction", (), {"member": type("Member", (), {"permissions": PERMISSION_VOICE_MOVE_MEMBERS})()})()
    admin = type("Interaction", (), {"member": type("Member", (), {"permissions": PERMISSION_ADMINISTRATOR})()})()
    plain = type("Interaction", (), {"member": type("Member", (), {"permissions": PERMISSION_MANAGE_GUILD})()})()
    allowlisted = type("Interaction", (), {"member": type("Member", (), {"permissions": 0, "user": FakeUser("u1")})()})()

    assert can_use_shuffle_command(manage, None)
    assert can_use_shuffle_command(admin, None)
    assert can_use_shuffle_command(allowlisted, ["u1"])
    assert not can_use_shuffle_command(plain, None)


def test_shuffle_application_command_has_no_default_permissions() -> None:
    command = shuffle_application_command()
    assert command.default_member_permissions is None
