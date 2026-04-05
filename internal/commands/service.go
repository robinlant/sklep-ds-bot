package commands

import (
	"context"
	"fmt"
	"strings"

	"github.com/robinlant/sklep-ds-bot/internal/domain"
)

type Repository interface {
	GetGuildSettings(context.Context, string) (*domain.GuildSettings, error)
	UpsertGuildSettings(context.Context, *domain.GuildSettings) error
}

type Service struct {
	repo Repository
}

func New(repo Repository) *Service {
	return &Service{repo: repo}
}

func (s *Service) GetGuildSettings(ctx context.Context, guildID string) (domain.GuildSettings, error) {
	if s.repo == nil {
		return domain.NewGuildSettings(guildID, domain.GuildTrackingModeAll, nil, ""), nil
	}
	settings, err := s.repo.GetGuildSettings(ctx, guildID)
	if err != nil {
		return domain.GuildSettings{}, err
	}
	if settings == nil {
		return domain.NewGuildSettings(guildID, domain.GuildTrackingModeAll, nil, ""), nil
	}
	return *settings, nil
}

func (s *Service) SetTrackingMode(ctx context.Context, guildID, mode string) (domain.GuildSettings, error) {
	settings, err := s.GetGuildSettings(ctx, guildID)
	if err != nil {
		return domain.GuildSettings{}, err
	}
	settings.TrackingMode = domain.NormalizeTrackingMode(mode)
	return settings, s.save(ctx, settings)
}

func (s *Service) SetTrackedChannelIDs(ctx context.Context, guildID string, ids []string) (domain.GuildSettings, error) {
	settings, err := s.GetGuildSettings(ctx, guildID)
	if err != nil {
		return domain.GuildSettings{}, err
	}
	settings.TrackedChannelIDs = domain.CleanChannelIDs(ids)
	if len(settings.TrackedChannelIDs) == 0 {
		settings.TrackingMode = domain.GuildTrackingModeNone
	} else {
		settings.TrackingMode = domain.GuildTrackingModeSpecific
	}
	return settings, s.save(ctx, settings)
}

func (s *Service) SetSummaryChannel(ctx context.Context, guildID, channelID string) (domain.GuildSettings, error) {
	settings, err := s.GetGuildSettings(ctx, guildID)
	if err != nil {
		return domain.GuildSettings{}, err
	}
	settings.SummaryChannelID = strings.TrimSpace(channelID)
	return settings, s.save(ctx, settings)
}

func (s *Service) ClearSummaryChannel(ctx context.Context, guildID string) (domain.GuildSettings, error) {
	return s.SetSummaryChannel(ctx, guildID, "")
}

func (s *Service) DescribeSettings(settings domain.GuildSettings) string {
	mode := domain.NormalizeTrackingMode(settings.TrackingMode)
	tracked := "all voice channels"
	if mode == domain.GuildTrackingModeNone {
		tracked = "no voice channels"
	} else if mode == domain.GuildTrackingModeSpecific {
		tracked = strings.Join(domain.CleanChannelIDs(settings.TrackedChannelIDs), ", ")
		if tracked == "" {
			tracked = "no configured channels"
		}
	}

	summaryChannel := settings.SummaryChannelID
	if summaryChannel == "" {
		summaryChannel = "not set"
	}

	var lines []string
	lines = append(lines, fmt.Sprintf("tracking mode: %s", mode))
	lines = append(lines, fmt.Sprintf("tracked channels: %s", tracked))
	lines = append(lines, fmt.Sprintf("summary channel: %s", summaryChannel))
	return strings.Join(lines, "\n")
}

func (s *Service) save(ctx context.Context, settings domain.GuildSettings) error {
	if s.repo == nil {
		return nil
	}
	settings.GuildID = strings.TrimSpace(settings.GuildID)
	settings.TrackingMode = domain.NormalizeTrackingMode(settings.TrackingMode)
	settings.TrackedChannelIDs = domain.CleanChannelIDs(settings.TrackedChannelIDs)
	return s.repo.UpsertGuildSettings(ctx, &settings)
}
