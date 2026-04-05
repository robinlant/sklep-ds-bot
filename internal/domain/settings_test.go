package domain

import "testing"

func TestGuildSettingsTracksChannel(t *testing.T) {
	tests := []struct {
		name     string
		settings GuildSettings
		channel  string
		want     bool
	}{
		{name: "all", settings: NewGuildSettings("g1", GuildTrackingModeAll, nil, ""), channel: "c1", want: true},
		{name: "none", settings: NewGuildSettings("g1", GuildTrackingModeNone, nil, ""), channel: "c1", want: false},
		{name: "specific match", settings: NewGuildSettings("g1", GuildTrackingModeSpecific, []string{"c1", "c2"}, ""), channel: "c2", want: true},
		{name: "specific miss", settings: NewGuildSettings("g1", GuildTrackingModeSpecific, []string{"c1", "c2"}, ""), channel: "c3", want: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.settings.TracksChannel(tt.channel); got != tt.want {
				t.Fatalf("TracksChannel() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestSummaryDestination(t *testing.T) {
	settings := NewGuildSettings("g1", GuildTrackingModeAll, nil, "summary-1")
	if got := settings.SummaryDestination("fallback"); got != "summary-1" {
		t.Fatalf("SummaryDestination() = %q, want %q", got, "summary-1")
	}

	settings.SummaryChannelID = ""
	if got := settings.SummaryDestination("fallback"); got != "fallback" {
		t.Fatalf("SummaryDestination() = %q, want %q", got, "fallback")
	}
}
