package tracker

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/robinlant/sklep-ds-bot/internal/domain"
)

type fakeRepo struct {
	settings map[string]domain.GuildSettings
	sessions map[string]domain.Session
	parts    map[string]domain.ParticipantInterval

	createSessionErr bool
	closeSessionErr  bool

	createdSessions []domain.Session
	closedEvents    []domain.SessionClosedEvent
	closedParts     []domain.ParticipantInterval
}

func newFakeRepo() *fakeRepo {
	return &fakeRepo{
		settings: map[string]domain.GuildSettings{},
		sessions: map[string]domain.Session{},
		parts:    map[string]domain.ParticipantInterval{},
	}
}

func (f *fakeRepo) GetGuildSettings(_ context.Context, guildID string) (*domain.GuildSettings, error) {
	settings, ok := f.settings[guildID]
	if !ok {
		return nil, nil
	}
	copy := settings
	return &copy, nil
}

func (f *fakeRepo) CreateSession(_ context.Context, session *domain.Session) error {
	if f.createSessionErr {
		return errors.New("create session failed")
	}
	f.sessions[session.ID] = *session
	f.createdSessions = append(f.createdSessions, *session)
	return nil
}

func (f *fakeRepo) FindActiveSession(_ context.Context, guildID, channelID string) (*domain.Session, error) {
	for _, session := range f.sessions {
		if session.GuildID == guildID && session.ChannelID == channelID && session.Status == domain.SessionStatusActive {
			copy := session
			return &copy, nil
		}
	}
	return nil, nil
}

func (f *fakeRepo) ListActiveSessions(_ context.Context) ([]domain.Session, error) {
	var out []domain.Session
	for _, session := range f.sessions {
		if session.Status == domain.SessionStatusActive {
			out = append(out, session)
		}
	}
	return out, nil
}

func (f *fakeRepo) ListClosedSessionsPendingNotification(_ context.Context) ([]domain.Session, error) {
	var out []domain.Session
	for _, session := range f.sessions {
		if session.Status == domain.SessionStatusClosed && session.ClosedEventPublishedAt == nil {
			out = append(out, session)
		}
	}
	return out, nil
}

func (f *fakeRepo) GetSessionByID(_ context.Context, sessionID string) (*domain.Session, error) {
	s, ok := f.sessions[sessionID]
	if !ok {
		return nil, nil
	}
	copy := s
	return &copy, nil
}

func (f *fakeRepo) CloseSession(_ context.Context, sessionID string, endedAt time.Time, endedByUserID string) error {
	if f.closeSessionErr {
		return errors.New("close session failed")
	}
	s := f.sessions[sessionID]
	s.Status = domain.SessionStatusClosed
	s.EndedAt = &endedAt
	s.EndedByUserID = endedByUserID
	f.sessions[sessionID] = s
	f.closedEvents = append(f.closedEvents, domain.SessionClosedEvent{SessionID: sessionID, EndedAt: endedAt, EndedByUserID: endedByUserID})
	return nil
}

func (f *fakeRepo) MarkSessionClosedEventPublished(_ context.Context, sessionID string, publishedAt time.Time) error {
	s := f.sessions[sessionID]
	s.ClosedEventPublishedAt = &publishedAt
	f.sessions[sessionID] = s
	return nil
}

func (f *fakeRepo) CreateParticipant(_ context.Context, participant *domain.ParticipantInterval) error {
	f.parts[participant.ID] = *participant
	return nil
}

func (f *fakeRepo) FindActiveParticipant(_ context.Context, sessionID, userID string) (*domain.ParticipantInterval, error) {
	for _, participant := range f.parts {
		if participant.SessionID == sessionID && participant.UserID == userID && participant.Active {
			copy := participant
			return &copy, nil
		}
	}
	return nil, nil
}

func (f *fakeRepo) ListActiveParticipants(_ context.Context, sessionID string) ([]domain.ParticipantInterval, error) {
	var out []domain.ParticipantInterval
	for _, participant := range f.parts {
		if participant.SessionID == sessionID && participant.Active {
			out = append(out, participant)
		}
	}
	return out, nil
}

func (f *fakeRepo) ListParticipantsBySession(_ context.Context, sessionID string) ([]domain.ParticipantInterval, error) {
	var out []domain.ParticipantInterval
	for _, participant := range f.parts {
		if participant.SessionID == sessionID {
			out = append(out, participant)
		}
	}
	return out, nil
}

func (f *fakeRepo) CloseParticipant(_ context.Context, participantID string, leftAt time.Time, durationMs int64) error {
	participant := f.parts[participantID]
	participant.Active = false
	participant.LeftAt = &leftAt
	participant.DurationMs = durationMs
	f.parts[participantID] = participant
	f.closedParts = append(f.closedParts, participant)
	return nil
}

type fakePublisher struct{ events []any }

func (f *fakePublisher) PublishJSON(_ context.Context, _ string, value any) error {
	f.events = append(f.events, value)
	return nil
}

func TestSessionCreatesAndCloses(t *testing.T) {
	repo := newFakeRepo()
	publisher := &fakePublisher{}
	svc := New(repo, publisher, Defaults{TrackingMode: domain.GuildTrackingModeAll})

	start := time.Date(2026, 4, 5, 18, 0, 0, 0, time.UTC)
	if err := svc.HandleVoiceEvent(context.Background(), domain.VoiceStateEvent{
		GuildID:    "g1",
		ChannelID:  "c1",
		UserID:     "u1",
		UserName:   "alice",
		OccurredAt: start,
	}); err != nil {
		t.Fatal(err)
	}

	if len(repo.createdSessions) != 1 {
		t.Fatalf("expected one session, got %d", len(repo.createdSessions))
	}
	if err := svc.HandleVoiceEvent(context.Background(), domain.VoiceStateEvent{
		GuildID:           "g1",
		PreviousChannelID: "c1",
		UserID:            "u1",
		OccurredAt:        start.Add(10 * time.Minute),
	}); err != nil {
		t.Fatal(err)
	}
	if len(repo.closedParts) != 1 {
		t.Fatalf("expected one closed participant, got %d", len(repo.closedParts))
	}
	if len(publisher.events) != 1 {
		t.Fatalf("expected one closed session event, got %d", len(publisher.events))
	}
}

func TestSessionMovePublishesCloseEvenIfJoinFails(t *testing.T) {
	repo := newFakeRepo()
	publisher := &fakePublisher{}
	svc := New(repo, publisher, Defaults{TrackingMode: domain.GuildTrackingModeAll})
	start := time.Date(2026, 4, 5, 18, 0, 0, 0, time.UTC)

	if err := svc.HandleVoiceEvent(context.Background(), domain.VoiceStateEvent{GuildID: "g1", ChannelID: "c1", UserID: "u1", UserName: "alice", OccurredAt: start}); err != nil {
		t.Fatal(err)
	}
	repo.createSessionErr = true
	if err := svc.HandleVoiceEvent(context.Background(), domain.VoiceStateEvent{GuildID: "g1", PreviousChannelID: "c1", ChannelID: "c2", UserID: "u1", UserName: "alice", OccurredAt: start.Add(time.Minute)}); err == nil {
		t.Fatal("expected join failure")
	}
	if len(publisher.events) != 1 {
		t.Fatalf("expected old session close to be published, got %d events", len(publisher.events))
	}
}

func TestStartRecoversZombieSession(t *testing.T) {
	repo := newFakeRepo()
	publisher := &fakePublisher{}
	svc := New(repo, publisher, Defaults{TrackingMode: domain.GuildTrackingModeAll})
	start := time.Date(2026, 4, 5, 18, 0, 0, 0, time.UTC)
	end := start.Add(12 * time.Minute)
	session := domain.Session{ID: "s1", GuildID: "g1", ChannelID: "c1", Status: domain.SessionStatusActive, StartedAt: start}
	repo.sessions[session.ID] = session
	repo.parts["p1"] = domain.ParticipantInterval{ID: "p1", SessionID: session.ID, GuildID: "g1", ChannelID: "c1", UserID: "u1", UserName: "alice", JoinedAt: start, LeftAt: &end, DurationMs: int64(12 * time.Minute / time.Millisecond), Active: false}

	if err := svc.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := repo.sessions[session.ID].Status; got != domain.SessionStatusClosed {
		t.Fatalf("session status = %q, want closed", got)
	}
	if len(publisher.events) != 1 {
		t.Fatalf("expected recovered close to be published, got %d events", len(publisher.events))
	}
}

func TestStartRepublishesPendingClosedSession(t *testing.T) {
	repo := newFakeRepo()
	publisher := &fakePublisher{}
	svc := New(repo, publisher, Defaults{TrackingMode: domain.GuildTrackingModeAll})
	start := time.Date(2026, 4, 5, 18, 0, 0, 0, time.UTC)
	end := start.Add(1 * time.Minute)
	session := domain.Session{ID: "s1", GuildID: "g1", ChannelID: "c1", Status: domain.SessionStatusClosed, StartedAt: start, EndedAt: &end}
	repo.sessions[session.ID] = session

	if err := svc.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	if repo.sessions[session.ID].ClosedEventPublishedAt == nil {
		t.Fatal("expected pending closed event to be marked published")
	}
	if len(publisher.events) != 1 {
		t.Fatalf("expected pending close to be republished once, got %d", len(publisher.events))
	}
}
