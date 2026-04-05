package domain

import (
	"sort"
	"strings"
	"time"
)

const (
	GuildTrackingModeAll      = "all"
	GuildTrackingModeNone     = "none"
	GuildTrackingModeSpecific = "specific"
)

type GuildSettings struct {
	GuildID           string    `bson:"_id,omitempty" json:"guildId"`
	TrackingMode      string    `bson:"trackingMode" json:"trackingMode"`
	TrackedChannelIDs []string  `bson:"trackedChannelIds,omitempty" json:"trackedChannelIds,omitempty"`
	SummaryChannelID  string    `bson:"summaryChannelId,omitempty" json:"summaryChannelId,omitempty"`
	CreatedAt         time.Time `bson:"createdAt" json:"createdAt"`
	UpdatedAt         time.Time `bson:"updatedAt" json:"updatedAt"`
}

func CleanChannelIDs(ids []string) []string {
	seen := make(map[string]struct{}, len(ids))
	out := make([]string, 0, len(ids))
	for _, id := range ids {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		out = append(out, id)
	}
	sort.Strings(out)
	return out
}

func NormalizeTrackingMode(mode string) string {
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case GuildTrackingModeAll:
		return GuildTrackingModeAll
	case GuildTrackingModeNone:
		return GuildTrackingModeNone
	case GuildTrackingModeSpecific:
		return GuildTrackingModeSpecific
	default:
		return GuildTrackingModeAll
	}
}

func NewGuildSettings(guildID, trackingMode string, trackedChannelIDs []string, summaryChannelID string) GuildSettings {
	return GuildSettings{
		GuildID:           strings.TrimSpace(guildID),
		TrackingMode:      NormalizeTrackingMode(trackingMode),
		TrackedChannelIDs: CleanChannelIDs(trackedChannelIDs),
		SummaryChannelID:  strings.TrimSpace(summaryChannelID),
	}
}

func (s GuildSettings) TracksChannel(channelID string) bool {
	channelID = strings.TrimSpace(channelID)
	if channelID == "" {
		return false
	}

	switch NormalizeTrackingMode(s.TrackingMode) {
	case GuildTrackingModeNone:
		return false
	case GuildTrackingModeAll:
		return true
	case GuildTrackingModeSpecific:
		for _, id := range CleanChannelIDs(s.TrackedChannelIDs) {
			if id == channelID {
				return true
			}
		}
		return false
	default:
		return true
	}
}

func (s GuildSettings) SummaryDestination(fallbackChannelID string) string {
	if channelID := strings.TrimSpace(s.SummaryChannelID); channelID != "" {
		return channelID
	}
	return strings.TrimSpace(fallbackChannelID)
}
