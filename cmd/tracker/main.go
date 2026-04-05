package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/robinlant/sklep-ds-bot/internal/bus"
	"github.com/robinlant/sklep-ds-bot/internal/config"
	"github.com/robinlant/sklep-ds-bot/internal/domain"
	mongorepo "github.com/robinlant/sklep-ds-bot/internal/mongo"
	"github.com/robinlant/sklep-ds-bot/internal/tracker"

	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatal(err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	mongoClient, err := mongo.Connect(ctx, options.Client().ApplyURI(cfg.MongoURI))
	if err != nil {
		log.Fatal(err)
	}
	defer func() { _ = mongoClient.Disconnect(context.Background()) }()

	repo := mongorepo.NewRepository(mongoClient.Database(cfg.MongoDB))
	if err := repo.EnsureIndexes(ctx); err != nil {
		log.Fatal(err)
	}

	if cfg.EventSigningSecret == "" {
		log.Fatal("EVENT_SIGNING_SECRET is required")
	}
	busConn, err := bus.Connect(cfg.NATSURL, cfg.EventSigningSecret, "tracker")
	if err != nil {
		log.Fatal(err)
	}
	defer busConn.Close()

	service := tracker.New(repo, busConn, tracker.Defaults{
		TrackingMode:      cfg.TrackingMode,
		TrackedChannelIDs: cfg.TrackedChannelIDs,
	})

	_, err = busConn.Subscribe(ctx, domain.SubjectVoiceEvent, repo, func(payload []byte) error {
		var event domain.VoiceStateEvent
		if err := json.Unmarshal(payload, &event); err != nil {
			return err
		}
		return service.HandleVoiceEvent(ctx, event)
	})
	if err != nil {
		log.Fatal(err)
	}

	if err := service.Start(ctx); err != nil {
		log.Fatal(err)
	}

	<-ctx.Done()
}
