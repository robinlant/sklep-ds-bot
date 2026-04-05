package domain

import "time"

const (
	SubjectVoiceEvent    = "voice.events"
	SubjectSessionClosed = "session.closed"
	SubjectSummaryReady  = "session.summary"
)

type VoiceStateEvent struct {
	GuildID           string    `json:"guildId"`
	UserID            string    `json:"userId"`
	UserName          string    `json:"userName"`
	ChannelID         string    `json:"channelId"`
	PreviousChannelID string    `json:"previousChannelId"`
	IsBot             bool      `json:"isBot"`
	OccurredAt        time.Time `json:"occurredAt"`
}

type SessionClosedEvent struct {
	SessionID     string    `json:"sessionId"`
	GuildID       string    `json:"guildId"`
	ChannelID     string    `json:"channelId"`
	StartedAt     time.Time `json:"startedAt"`
	EndedAt       time.Time `json:"endedAt"`
	EndedByUserID string    `json:"endedByUserId"`
}

type SummaryReadyEvent struct {
	SessionID string `json:"sessionId"`
	GuildID   string `json:"guildId"`
	ChannelID string `json:"channelId"`
	Message   string `json:"message"`
}
