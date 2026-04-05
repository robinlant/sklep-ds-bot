package domain

import "time"

const (
	SessionStatusActive = "active"
	SessionStatusClosed = "closed"
)

type Session struct {
	ID                       string     `bson:"_id,omitempty" json:"id"`
	GuildID                  string     `bson:"guildId" json:"guildId"`
	ChannelID                string     `bson:"channelId" json:"channelId"`
	Status                   string     `bson:"status" json:"status"`
	StartedAt                time.Time  `bson:"startedAt" json:"startedAt"`
	EndedAt                  *time.Time `bson:"endedAt,omitempty" json:"endedAt,omitempty"`
	EndedByUserID            string     `bson:"endedByUserId,omitempty" json:"endedByUserId,omitempty"`
	ClosedEventPublishedAt   *time.Time `bson:"closedEventPublishedAt,omitempty" json:"closedEventPublishedAt,omitempty"`
	SummaryChannelID         string     `bson:"summaryChannelId,omitempty" json:"summaryChannelId,omitempty"`
	SummaryMessage           string     `bson:"summaryMessage,omitempty" json:"summaryMessage,omitempty"`
	SummaryGeneratedAt       *time.Time `bson:"summaryGeneratedAt,omitempty" json:"summaryGeneratedAt,omitempty"`
	SummaryDeliveryClaimedAt *time.Time `bson:"summaryDeliveryClaimedAt,omitempty" json:"summaryDeliveryClaimedAt,omitempty"`
	SummaryDeliveredAt       *time.Time `bson:"summaryDeliveredAt,omitempty" json:"summaryDeliveredAt,omitempty"`
	CreatedAt                time.Time  `bson:"createdAt" json:"createdAt"`
	UpdatedAt                time.Time  `bson:"updatedAt" json:"updatedAt"`
}

type ParticipantInterval struct {
	ID         string     `bson:"_id,omitempty" json:"id"`
	SessionID  string     `bson:"sessionId" json:"sessionId"`
	GuildID    string     `bson:"guildId" json:"guildId"`
	ChannelID  string     `bson:"channelId" json:"channelId"`
	UserID     string     `bson:"userId" json:"userId"`
	UserName   string     `bson:"userName" json:"userName"`
	JoinedAt   time.Time  `bson:"joinedAt" json:"joinedAt"`
	LeftAt     *time.Time `bson:"leftAt,omitempty" json:"leftAt,omitempty"`
	DurationMs int64      `bson:"durationMs" json:"durationMs"`
	Active     bool       `bson:"active" json:"active"`
}

type ParticipantSummary struct {
	UserID    string        `json:"userId"`
	UserName  string        `json:"userName"`
	Intervals int           `json:"intervals"`
	TotalTime time.Duration `json:"totalTime"`
}

type SessionSummary struct {
	SessionID     string               `json:"sessionId"`
	GuildID       string               `json:"guildId"`
	ChannelID     string               `json:"channelId"`
	UniqueUsers   int                  `json:"uniqueUsers"`
	TotalDuration time.Duration        `json:"totalDuration"`
	EndedByUserID string               `json:"endedByUserId"`
	Participants  []ParticipantSummary `json:"participants"`
}
