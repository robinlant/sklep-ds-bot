package commands

import (
	"context"
	"testing"

	"github.com/robinlant/sklep-ds-bot/internal/domain"
)

type fakeRepo struct {
	settings map[string]domain.GuildSettings
}

func newFakeRepo() *fakeRepo {
	return &fakeRepo{settings: map[string]domain.GuildSettings{}}
}

func (f *fakeRepo) GetGuildSettings(_ context.Context, guildID string) (*domain.GuildSettings, error) {
	settings, ok := f.settings[guildID]
	if !ok {
		return nil, nil
	}
	copy := settings
	return &copy, nil
}

func (f *fakeRepo) UpsertGuildSettings(_ context.Context, settings *domain.GuildSettings) error {
	copy := *settings
	f.settings[settings.GuildID] = copy
	return nil
}

func TestSetTrackingMode(t *testing.T) {
	repo := newFakeRepo()
	svc := New(repo)

	settings, err := svc.SetTrackingMode(context.Background(), "g1", domain.GuildTrackingModeNone)
	if err != nil {
		t.Fatal(err)
	}
	if settings.TrackingMode != domain.GuildTrackingModeNone {
		t.Fatalf("tracking mode = %q, want %q", settings.TrackingMode, domain.GuildTrackingModeNone)
	}
}

func TestSetTrackedChannelIDs(t *testing.T) {
	repo := newFakeRepo()
	svc := New(repo)

	settings, err := svc.SetTrackedChannelIDs(context.Background(), "g1", []string{"c2", "c1", "c2"})
	if err != nil {
		t.Fatal(err)
	}
	if settings.TrackingMode != domain.GuildTrackingModeSpecific {
		t.Fatalf("tracking mode = %q, want %q", settings.TrackingMode, domain.GuildTrackingModeSpecific)
	}
	if len(settings.TrackedChannelIDs) != 2 || settings.TrackedChannelIDs[0] != "c1" || settings.TrackedChannelIDs[1] != "c2" {
		t.Fatalf("tracked ids = %#v, want sorted unique ids", settings.TrackedChannelIDs)
	}
}

func TestSetSummaryChannel(t *testing.T) {
	repo := newFakeRepo()
	svc := New(repo)

	settings, err := svc.SetSummaryChannel(context.Background(), "g1", "summary-1")
	if err != nil {
		t.Fatal(err)
	}
	if settings.SummaryChannelID != "summary-1" {
		t.Fatalf("summary channel = %q, want %q", settings.SummaryChannelID, "summary-1")
	}
}
