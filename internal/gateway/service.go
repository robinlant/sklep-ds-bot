package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/robinlant/sklep-ds-bot/internal/domain"

	"github.com/bwmarrin/discordgo"
)

type Publisher interface {
	PublishJSON(context.Context, string, any) error
}

type Service struct {
	session *discordgo.Session
	bus     Publisher
}

func New(session *discordgo.Session, bus Publisher) *Service {
	return &Service{session: session, bus: bus}
}

func (s *Service) Install() {
	s.session.AddHandler(func(ds *discordgo.Session, update *discordgo.VoiceStateUpdate) {
		event := voiceEventFromDiscord(ds, update)
		_ = s.bus.PublishJSON(context.Background(), domain.SubjectVoiceEvent, event)
	})
}

func voiceEventFromDiscord(ds *discordgo.Session, update *discordgo.VoiceStateUpdate) domain.VoiceStateEvent {
	if update == nil {
		return domain.VoiceStateEvent{}
	}

	var previous string
	if update.BeforeUpdate != nil {
		previous = update.BeforeUpdate.ChannelID
	}

	userName := ""
	isBot := false
	if ds != nil && ds.State != nil {
		if member, err := ds.State.Member(update.GuildID, update.UserID); err == nil && member != nil && member.User != nil {
			userName = member.User.Username
			isBot = member.User.Bot
		}
	}

	return domain.VoiceStateEvent{
		GuildID:           update.GuildID,
		UserID:            update.UserID,
		UserName:          userName,
		ChannelID:         update.ChannelID,
		PreviousChannelID: previous,
		IsBot:             isBot,
		OccurredAt:        time.Now().UTC(),
	}
}

func SummaryFromPayload(payload []byte) (domain.SummaryReadyEvent, error) {
	var event domain.SummaryReadyEvent
	if err := json.Unmarshal(payload, &event); err != nil {
		return domain.SummaryReadyEvent{}, fmt.Errorf("decode summary event: %w", err)
	}
	return event, nil
}
