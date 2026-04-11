from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from voice_tracker import domain
from voice_tracker.tracker import Defaults, Service


class FakeRepo:
    def __init__(self) -> None:
        self.settings: dict[str, domain.GuildSettings] = {}
        self.sessions: dict[str, domain.Session] = {}
        self.parts: dict[str, domain.ParticipantInterval] = {}
        self.create_session_err = False
        self.close_session_err = False
        self.created_sessions: list[domain.Session] = []
        self.closed_events: list[domain.SessionClosedEvent] = []
        self.closed_parts: list[domain.ParticipantInterval] = []

    def GetGuildSettings(self, guild_id: str) -> domain.GuildSettings | None:
        return self.settings.get(guild_id)

    def CreateSession(self, session: domain.Session) -> None:
        if self.create_session_err:
            raise RuntimeError("create session failed")
        self.sessions[session.id] = replace(session)
        self.created_sessions.append(replace(session))

    def FindActiveSession(self, guild_id: str, channel_id: str) -> domain.Session | None:
        for session in self.sessions.values():
            if session.guild_id == guild_id and session.channel_id == channel_id and session.status == domain.SESSION_STATUS_ACTIVE:
                return replace(session)
        return None

    def ListActiveSessions(self) -> list[domain.Session]:
        return [replace(session) for session in self.sessions.values() if session.status == domain.SESSION_STATUS_ACTIVE]

    def ListClosedSessionsPendingNotification(self) -> list[domain.Session]:
        return [replace(session) for session in self.sessions.values() if session.status == domain.SESSION_STATUS_CLOSED and session.closed_event_published_at is None]

    def GetSessionByID(self, session_id: str) -> domain.Session | None:
        session = self.sessions.get(session_id)
        return None if session is None else replace(session)

    def CloseSession(self, session_id: str, ended_at: datetime, ended_by_user_id: str) -> None:
        if self.close_session_err:
            raise RuntimeError("close session failed")
        session = self.sessions[session_id]
        session.status = domain.SESSION_STATUS_CLOSED
        session.ended_at = ended_at
        session.ended_by_user_id = ended_by_user_id
        self.sessions[session_id] = session
        self.closed_events.append(domain.SessionClosedEvent(session_id=session_id, ended_at=ended_at, ended_by_user_id=ended_by_user_id))

    def MarkSessionClosedEventPublished(self, session_id: str, published_at: datetime) -> None:
        session = self.sessions[session_id]
        session.closed_event_published_at = published_at
        self.sessions[session_id] = session

    def CreateParticipant(self, participant: domain.ParticipantInterval) -> None:
        self.parts[participant.id] = replace(participant)

    def FindActiveParticipant(self, session_id: str, user_id: str) -> domain.ParticipantInterval | None:
        for participant in self.parts.values():
            if participant.session_id == session_id and participant.user_id == user_id and participant.active:
                return replace(participant)
        return None

    def ListActiveParticipants(self, session_id: str) -> list[domain.ParticipantInterval]:
        return [replace(participant) for participant in self.parts.values() if participant.session_id == session_id and participant.active]

    def ListParticipantsBySession(self, session_id: str) -> list[domain.ParticipantInterval]:
        return [replace(participant) for participant in self.parts.values() if participant.session_id == session_id]

    def CloseParticipant(self, participant_id: str, left_at: datetime, duration_ms: int) -> None:
        participant = self.parts[participant_id]
        participant.active = False
        participant.left_at = left_at
        participant.duration_ms = duration_ms
        self.parts[participant_id] = participant
        self.closed_parts.append(replace(participant))


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish_json(self, _subject: str, value: object) -> None:
        self.events.append(value)


@pytest.mark.asyncio
async def test_session_creates_and_closes() -> None:
    repo = FakeRepo()
    publisher = FakePublisher()
    svc = Service(repo, publisher, Defaults(tracking_mode=domain.GUILD_TRACKING_MODE_ALL))

    start = datetime(2026, 4, 5, 18, 0, 0, tzinfo=UTC)
    await svc.HandleVoiceEvent(
        domain.VoiceStateEvent(
            guild_id="g1",
            channel_id="c1",
            user_id="u1",
            user_name="alice",
            occurred_at=start,
        )
    )

    assert len(repo.created_sessions) == 1
    await svc.HandleVoiceEvent(
        domain.VoiceStateEvent(
            guild_id="g1",
            previous_channel_id="c1",
            user_id="u1",
            occurred_at=start + timedelta(minutes=10),
        )
    )
    assert len(repo.closed_parts) == 1
    assert len(publisher.events) == 1


@pytest.mark.asyncio
async def test_session_move_publishes_close_even_if_join_fails() -> None:
    repo = FakeRepo()
    publisher = FakePublisher()
    svc = Service(repo, publisher, Defaults(tracking_mode=domain.GUILD_TRACKING_MODE_ALL))
    start = datetime(2026, 4, 5, 18, 0, 0, tzinfo=UTC)

    await svc.HandleVoiceEvent(
        domain.VoiceStateEvent(guild_id="g1", channel_id="c1", user_id="u1", user_name="alice", occurred_at=start)
    )
    repo.create_session_err = True

    with pytest.raises(RuntimeError, match="create session failed"):
        await svc.HandleVoiceEvent(
            domain.VoiceStateEvent(
                guild_id="g1",
                previous_channel_id="c1",
                channel_id="c2",
                user_id="u1",
                user_name="alice",
                occurred_at=start + timedelta(minutes=1),
            )
        )

    assert len(publisher.events) == 1


@pytest.mark.asyncio
async def test_start_recovers_zombie_session() -> None:
    repo = FakeRepo()
    publisher = FakePublisher()
    svc = Service(repo, publisher, Defaults(tracking_mode=domain.GUILD_TRACKING_MODE_ALL))
    start = datetime(2026, 4, 5, 18, 0, 0, tzinfo=UTC)
    end = start + timedelta(minutes=12)
    session = domain.Session(id="s1", guild_id="g1", channel_id="c1", status=domain.SESSION_STATUS_ACTIVE, started_at=start)
    repo.sessions[session.id] = session
    repo.parts["p1"] = domain.ParticipantInterval(
        id="p1",
        session_id=session.id,
        guild_id="g1",
        channel_id="c1",
        user_id="u1",
        user_name="alice",
        joined_at=start,
        left_at=end,
        duration_ms=int(timedelta(minutes=12).total_seconds() * 1000),
        active=False,
    )

    await svc.Start()
    assert repo.sessions[session.id].status == domain.SESSION_STATUS_CLOSED
    assert len(publisher.events) == 1


@pytest.mark.asyncio
async def test_start_republishes_pending_closed_session() -> None:
    repo = FakeRepo()
    publisher = FakePublisher()
    svc = Service(repo, publisher, Defaults(tracking_mode=domain.GUILD_TRACKING_MODE_ALL))
    start = datetime(2026, 4, 5, 18, 0, 0, tzinfo=UTC)
    end = start + timedelta(minutes=1)
    session = domain.Session(id="s1", guild_id="g1", channel_id="c1", status=domain.SESSION_STATUS_CLOSED, started_at=start, ended_at=end)
    repo.sessions[session.id] = session

    await svc.Start()
    assert repo.sessions[session.id].closed_event_published_at is not None
    assert len(publisher.events) == 1
