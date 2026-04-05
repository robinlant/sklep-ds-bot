package commands

import (
	"context"
	"fmt"
	"strings"

	"github.com/robinlant/sklep-ds-bot/internal/domain"

	"github.com/bwmarrin/discordgo"
)

const (
	commandTrackMode      = "voice-track-mode"
	commandTrackChannels  = "voice-track-channels"
	commandSummaryChannel = "voice-summary-channel"
	commandSettings       = "voice-settings"
)

func RegisterCommands(ctx context.Context, session *discordgo.Session, appID, guildID string) error {
	if session == nil || strings.TrimSpace(appID) == "" {
		return nil
	}
	commands := []*discordgo.ApplicationCommand{
		{
			Name:        commandTrackMode,
			Description: "Set how voice channels are tracked",
			Options: []*discordgo.ApplicationCommandOption{{
				Type:        discordgo.ApplicationCommandOptionString,
				Name:        "mode",
				Description: "all, none, or specific",
				Required:    true,
				Choices: []*discordgo.ApplicationCommandOptionChoice{
					{Name: domain.GuildTrackingModeAll, Value: domain.GuildTrackingModeAll},
					{Name: domain.GuildTrackingModeNone, Value: domain.GuildTrackingModeNone},
					{Name: domain.GuildTrackingModeSpecific, Value: domain.GuildTrackingModeSpecific},
				},
			}},
		},
		{
			Name:        commandTrackChannels,
			Description: "Set the tracked voice channels",
			Options: []*discordgo.ApplicationCommandOption{{
				Type:        discordgo.ApplicationCommandOptionString,
				Name:        "channels",
				Description: "Comma-separated channel IDs or mentions",
				Required:    true,
			}},
		},
		{
			Name:        commandSummaryChannel,
			Description: "Set where summaries are posted",
			Options: []*discordgo.ApplicationCommandOption{{
				Type:        discordgo.ApplicationCommandOptionChannel,
				Name:        "channel",
				Description: "Destination text channel",
				Required:    true,
			}},
		},
		{Name: commandSettings, Description: "Show the current voice settings"},
	}
	_, err := session.ApplicationCommandBulkOverwrite(appID, guildID, commands)
	return err
}

func (s *Service) Install(session *discordgo.Session, allowedGuildID string) {
	session.AddHandler(func(ds *discordgo.Session, interaction *discordgo.InteractionCreate) {
		if interaction.Type != discordgo.InteractionApplicationCommand {
			return
		}
		data := interaction.ApplicationCommandData()
		if interaction.GuildID == "" {
			return
		}
		if strings.TrimSpace(allowedGuildID) != "" && interaction.GuildID != allowedGuildID {
			return
		}
		if !hasManagePermissions(interaction) {
			_ = respondEphemeral(ds, interaction, "insufficient permissions")
			return
		}

		var content string
		var err error
		switch data.Name {
		case commandTrackMode:
			mode := stringOption(data.Options, 0)
			_, err = s.SetTrackingMode(context.Background(), interaction.GuildID, mode)
			content = fmt.Sprintf("tracking mode set to %s", domain.NormalizeTrackingMode(mode))
		case commandTrackChannels:
			channels := parseChannelIDs(stringOption(data.Options, 0))
			_, err = s.SetTrackedChannelIDs(context.Background(), interaction.GuildID, channels)
			content = fmt.Sprintf("tracked channels updated (%d)", len(channels))
		case commandSummaryChannel:
			channel := channelOptionID(data.Options, 0)
			_, err = s.SetSummaryChannel(context.Background(), interaction.GuildID, channel)
			content = fmt.Sprintf("summary channel set to %s", channel)
		case commandSettings:
			settings, settingsErr := s.GetGuildSettings(context.Background(), interaction.GuildID)
			if settingsErr != nil {
				err = settingsErr
			} else {
				content = s.DescribeSettings(settings)
			}
		default:
			return
		}
		if err != nil {
			content = err.Error()
		}
		_ = respondEphemeral(ds, interaction, content)
	})
}

func hasManagePermissions(interaction *discordgo.InteractionCreate) bool {
	if interaction == nil || interaction.Member == nil {
		return false
	}
	permissions := interaction.Member.Permissions
	allowed := permissions&(discordgo.PermissionAdministrator|discordgo.PermissionManageGuild) != 0
	return allowed
}

func stringOption(options []*discordgo.ApplicationCommandInteractionDataOption, index int) string {
	if index < 0 || index >= len(options) {
		return ""
	}
	if v, ok := options[index].Value.(string); ok {
		return v
	}
	return ""
}

func channelOptionID(options []*discordgo.ApplicationCommandInteractionDataOption, index int) string {
	if index < 0 || index >= len(options) {
		return ""
	}
	if options[index].Value == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(options[index].Value))
}

func parseChannelIDs(raw string) []string {
	fields := strings.FieldsFunc(raw, func(r rune) bool {
		switch r {
		case ',', ' ', '\n', '\t':
			return true
		default:
			return false
		}
	})
	out := make([]string, 0, len(fields))
	for _, field := range fields {
		field = strings.TrimSpace(field)
		field = strings.TrimPrefix(field, "<#")
		field = strings.TrimSuffix(field, ">")
		if field != "" {
			out = append(out, field)
		}
	}
	return out
}

func respondEphemeral(session *discordgo.Session, interaction *discordgo.InteractionCreate, content string) error {
	return session.InteractionRespond(interaction.Interaction, &discordgo.InteractionResponse{
		Type: discordgo.InteractionResponseChannelMessageWithSource,
		Data: &discordgo.InteractionResponseData{
			Content: content,
			Flags:   discordgo.MessageFlagsEphemeral,
		},
	})
}
