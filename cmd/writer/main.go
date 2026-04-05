package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/robinlant/sklep-ds-bot/internal/bus"
	"github.com/robinlant/sklep-ds-bot/internal/config"
	"github.com/robinlant/sklep-ds-bot/internal/domain"
	mongorepo "github.com/robinlant/sklep-ds-bot/internal/mongo"
	"github.com/robinlant/sklep-ds-bot/internal/summary"

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
	busConn, err := bus.Connect(cfg.NATSURL, cfg.EventSigningSecret, "writer")
	if err != nil {
		log.Fatal(err)
	}
	defer busConn.Close()

	service := summary.New(repo, busConn)
	_, err = busConn.Subscribe(ctx, domain.SubjectSessionClosed, repo, func(payload []byte) error {
		return service.HandleSessionClosed(ctx, payload)
	})
	if err != nil {
		log.Fatal(err)
	}

	if err := service.Start(ctx); err != nil {
		log.Fatal(err)
	}
	go func() {
		ticker := time.NewTicker(time.Minute)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := service.Start(ctx); err != nil {
					log.Printf("writer sweep error: %v", err)
				}
			}
		}
	}()

	<-ctx.Done()
}
