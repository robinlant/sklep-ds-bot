package tracker

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/robinlant/sklep-ds-bot/internal/domain"

	"github.com/google/uuid"
)

type Repository interface {
	GetGuildSettings(context.Context, string) (*domain.GuildSettings, error)
	CreateSession(context.Context, *domain.Session) error
	FindActiveSession(context.Context, string, string) (*domain.Session, error)
	ListActiveSessions(context.Context) ([]domain.Session, error)
	ListClosedSessionsPendingNotification(context.Context) ([]domain.Session, error)
	GetSessionByID(context.Context, string) (*domain.Session, error)
	CloseSession(context.Context, string, time.Time, string) error
	MarkSessionClosedEventPublished(context.Context, string, time.Time) error
	CreateParticipant(context.Context, *domain.ParticipantInterval) error
	FindActiveParticipant(context.Context, string, string) (*domain.ParticipantInterval, error)
	ListActiveParticipants(context.Context, string) ([]domain.ParticipantInterval, error)
	ListParticipantsBySession(context.Context, string) ([]domain.ParticipantInterval, error)
	CloseParticipant(context.Context, string, time.Time, int64) error
}

type Defaults struct {
	TrackingMode      string
	TrackedChannelIDs []string
}

type Publisher interface {
	PublishJSON(context.Context, string, any) error
}

type activeSession struct {
	Session      domain.Session
	Participants map[string]*activeParticipant
	UniqueUsers  map[string]struct{}
}

type activeParticipant struct {
	ID       string
	UserID   string
	UserName string
	JoinedAt time.Time
}

type Service struct {
	repo      Repository
	publisher Publisher
	channels  map[string]struct{}
	defaults  domain.GuildSettings

	mu       sync.Mutex
	sessions map[string]*activeSession
}

func New(repo Repository, publisher Publisher, defaults Defaults) *Service {
	channels := make(map[string]struct{}, len(defaults.TrackedChannelIDs))
	for _, id := range defaults.TrackedChannelIDs {
		if id != "" {
			channels[id] = struct{}{}
		}
	}
	return &Service{
		repo:      repo,
		publisher: publisher,
		channels:  channels,
		defaults:  domain.NewGuildSettings("", defaults.TrackingMode, defaults.TrackedChannelIDs, ""),
		sessions:  make(map[string]*activeSession),
	}
}

func (s *Service) Start(ctx context.Context) error {
	active, err := s.repo.ListActiveSessions(ctx)
	if err != nil {
		return err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	for _, session := range active {
		participants, err := s.repo.ListActiveParticipants(ctx, session.ID)
		if err != nil {
			continue
		}
		if len(participants) == 0 {
			allParticipants, err := s.repo.ListParticipantsBySession(ctx, session.ID)
			if err != nil {
				continue
			}
			endedAt, endedByUserID := latestParticipantEnd(allParticipants)
			if endedAt.IsZero() {
				endedAt = time.Now().UTC()
			}
			if err := s.repo.CloseSession(ctx, session.ID, endedAt, endedByUserID); err != nil {
				continue
			}
			if s.publisher != nil {
				if err := s.publisher.PublishJSON(ctx, domain.SubjectSessionClosed, domain.SessionClosedEvent{
					SessionID:     session.ID,
					GuildID:       session.GuildID,
					ChannelID:     session.ChannelID,
					StartedAt:     session.StartedAt,
					EndedAt:       endedAt,
					EndedByUserID: endedByUserID,
				}); err != nil {
					continue
				}
				if err := s.repo.MarkSessionClosedEventPublished(ctx, session.ID, time.Now().UTC()); err != nil {
					continue
				}
			}
			continue
		}
		state := &activeSession{
			Session:      session,
			Participants: make(map[string]*activeParticipant),
			UniqueUsers:  make(map[string]struct{}),
		}
		for _, participant := range participants {
			state.Participants[participant.UserID] = &activeParticipant{
				ID:       participant.ID,
				UserID:   participant.UserID,
				UserName: participant.UserName,
				JoinedAt: participant.JoinedAt,
			}
			state.UniqueUsers[participant.UserID] = struct{}{}
		}
		s.sessions[sessionKey(session.GuildID, session.ChannelID)] = state
	}

	pending, err := s.repo.ListClosedSessionsPendingNotification(ctx)
	if err != nil {
		return err
	}
	for _, session := range pending {
		if s.publisher == nil {
			continue
		}
		closed := &domain.SessionClosedEvent{
			SessionID:     session.ID,
			GuildID:       session.GuildID,
			ChannelID:     session.ChannelID,
			StartedAt:     session.StartedAt,
			EndedAt:       derefTime(session.EndedAt),
			EndedByUserID: session.EndedByUserID,
		}
		if err := s.publisher.PublishJSON(ctx, domain.SubjectSessionClosed, closed); err != nil {
			continue
		}
		if err := s.repo.MarkSessionClosedEventPublished(ctx, session.ID, time.Now().UTC()); err != nil {
			continue
		}
	}

	return nil
}

func (s *Service) HandleVoiceEvent(ctx context.Context, event domain.VoiceStateEvent) error {
	if event.IsBot {
		return nil
	}
	if event.OccurredAt.IsZero() {
		event.OccurredAt = time.Now().UTC()
	}

	if event.PreviousChannelID != "" && event.PreviousChannelID != event.ChannelID {
		closed, err := s.leave(ctx, event.GuildID, event.PreviousChannelID, event.UserID, event.OccurredAt)
		if err != nil {
			return err
		}
		if err := s.publishClosed(ctx, closed); err != nil {
			return err
		}
		if closed != nil {
			if err := s.repo.MarkSessionClosedEventPublished(ctx, closed.SessionID, time.Now().UTC()); err != nil {
				return err
			}
		}
		if event.ChannelID != "" {
			if err := s.join(ctx, event); err != nil {
				return err
			}
		}
		return nil
	}

	if event.ChannelID == "" {
		closed, err := s.leave(ctx, event.GuildID, event.PreviousChannelID, event.UserID, event.OccurredAt)
		if err != nil {
			return err
		}
		if err := s.publishClosed(ctx, closed); err != nil {
			return err
		}
		if closed != nil {
			return s.repo.MarkSessionClosedEventPublished(ctx, closed.SessionID, time.Now().UTC())
		}
		return nil
	}

	return s.join(ctx, event)
}

func (s *Service) join(ctx context.Context, event domain.VoiceStateEvent) error {
	settings, err := s.settingsForGuild(ctx, event.GuildID)
	if err != nil {
		return err
	}
	if !settings.TracksChannel(event.ChannelID) {
		return nil
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	key := sessionKey(event.GuildID, event.ChannelID)
	state, ok := s.sessions[key]
	if !ok {
		session := domain.Session{
			ID:        uuid.NewString(),
			GuildID:   event.GuildID,
			ChannelID: event.ChannelID,
			Status:    domain.SessionStatusActive,
			StartedAt: event.OccurredAt,
			CreatedAt: event.OccurredAt,
			UpdatedAt: event.OccurredAt,
		}
		if err := s.repo.CreateSession(ctx, &session); err != nil {
			return err
		}
		state = &activeSession{
			Session:      session,
			Participants: make(map[string]*activeParticipant),
			UniqueUsers:  make(map[string]struct{}),
		}
		s.sessions[key] = state
	}

	if _, exists := state.Participants[event.UserID]; exists {
		return nil
	}

	participant := &domain.ParticipantInterval{
		ID:        uuid.NewString(),
		SessionID: state.Session.ID,
		GuildID:   event.GuildID,
		ChannelID: event.ChannelID,
		UserID:    event.UserID,
		UserName:  event.UserName,
		JoinedAt:  event.OccurredAt,
		Active:    true,
	}
	if err := s.repo.CreateParticipant(ctx, participant); err != nil {
		return err
	}

	state.Participants[event.UserID] = &activeParticipant{
		ID:       participant.ID,
		UserID:   participant.UserID,
		UserName: participant.UserName,
		JoinedAt: participant.JoinedAt,
	}
	state.UniqueUsers[event.UserID] = struct{}{}
	return nil
}

func (s *Service) leave(ctx context.Context, guildID, channelID, userID string, occurredAt time.Time) (*domain.SessionClosedEvent, error) {
	settings, err := s.settingsForGuild(ctx, guildID)
	if err != nil {
		return nil, err
	}
	if channelID == "" || !settings.TracksChannel(channelID) {
		return nil, nil
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	state, ok := s.sessions[sessionKey(guildID, channelID)]
	if !ok {
		return nil, nil
	}

	participant, ok := state.Participants[userID]
	if !ok {
		return nil, nil
	}

	durationMs := occurredAt.Sub(participant.JoinedAt).Milliseconds()
	if durationMs < 0 {
		durationMs = 0
	}
	if err := s.repo.CloseParticipant(ctx, participant.ID, occurredAt, durationMs); err != nil {
		return nil, err
	}

	delete(state.Participants, userID)

	if len(state.Participants) > 0 {
		return nil, nil
	}

	if err := s.repo.CloseSession(ctx, state.Session.ID, occurredAt, userID); err != nil {
		return nil, err
	}
	delete(s.sessions, sessionKey(guildID, channelID))

	return &domain.SessionClosedEvent{
		SessionID:     state.Session.ID,
		GuildID:       guildID,
		ChannelID:     channelID,
		StartedAt:     state.Session.StartedAt,
		EndedAt:       occurredAt,
		EndedByUserID: userID,
	}, nil
}

func (s *Service) settingsForGuild(ctx context.Context, guildID string) (domain.GuildSettings, error) {
	if s.repo != nil {
		if settings, err := s.repo.GetGuildSettings(ctx, guildID); err != nil {
			return domain.GuildSettings{}, err
		} else if settings != nil {
			return *settings, nil
		}
	}
	defaults := s.defaults
	defaults.GuildID = guildID
	defaults.TrackingMode = domain.NormalizeTrackingMode(defaults.TrackingMode)
	defaults.TrackedChannelIDs = domain.CleanChannelIDs(defaults.TrackedChannelIDs)
	return defaults, nil
}

func (s *Service) publishClosed(ctx context.Context, closed *domain.SessionClosedEvent) error {
	if closed == nil || s.publisher == nil {
		return nil
	}
	return s.publisher.PublishJSON(ctx, domain.SubjectSessionClosed, closed)
}

func (s *Service) tracksChannel(channelID string) bool {
	if len(s.channels) == 0 {
		return true
	}
	_, ok := s.channels[channelID]
	return ok
}

func sessionKey(guildID, channelID string) string {
	return strings.Join([]string{guildID, channelID}, ":")
}

func DecodeVoiceEvent(data []byte) (domain.VoiceStateEvent, error) {
	var event domain.VoiceStateEvent
	if err := json.Unmarshal(data, &event); err != nil {
		return domain.VoiceStateEvent{}, fmt.Errorf("decode voice event: %w", err)
	}
	return event, nil
}

func latestParticipantEnd(participants []domain.ParticipantInterval) (time.Time, string) {
	var endedAt time.Time
	var endedByUserID string
	for _, participant := range participants {
		if participant.LeftAt == nil {
			continue
		}
		if participant.LeftAt.After(endedAt) {
			endedAt = *participant.LeftAt
			endedByUserID = participant.UserID
		}
	}
	return endedAt, endedByUserID
}

func derefTime(value *time.Time) time.Time {
	if value == nil {
		return time.Time{}
	}
	return *value
}
