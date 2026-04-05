package bus

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/nats-io/nats.go"
)

type Bus struct {
	conn   *nats.Conn
	secret []byte
	issuer string
	mu     sync.Mutex
	seen   map[string]int64
}

type Deduper interface {
	ClaimMessage(context.Context, string, string, string, int64) (bool, error)
}

type envelope struct {
	MessageID string          `json:"messageId"`
	Subject   string          `json:"subject"`
	Issuer    string          `json:"issuer"`
	IssuedAt  int64           `json:"issuedAt"`
	Payload   json.RawMessage `json:"payload"`
	Signature string          `json:"signature"`
}

func Connect(url, secret, issuer string) (*Bus, error) {
	if secret == "" {
		return nil, fmt.Errorf("event signing secret is required")
	}
	conn, err := nats.Connect(url)
	if err != nil {
		return nil, err
	}
	return &Bus{conn: conn, secret: []byte(secret), issuer: issuer, seen: make(map[string]int64)}, nil
}

func (b *Bus) Close() {
	if b != nil && b.conn != nil {
		b.conn.Close()
	}
}

func (b *Bus) PublishJSON(_ context.Context, subject string, value any) error {
	if b == nil || b.conn == nil {
		return fmt.Errorf("nats connection is nil")
	}
	payload, err := json.Marshal(value)
	if err != nil {
		return err
	}
	env := envelope{MessageID: uuid.NewString(), Subject: subject, Issuer: b.issuer, IssuedAt: time.Now().UTC().Unix(), Payload: payload}
	env.Signature = signEnvelope(b.secret, env.MessageID, env.Subject, env.Issuer, env.IssuedAt, env.Payload)
	body, err := json.Marshal(env)
	if err != nil {
		return err
	}
	return b.conn.Publish(subject, body)
}

func (b *Bus) Subscribe(ctx context.Context, subject string, deduper Deduper, handler func([]byte) error) (*nats.Subscription, error) {
	if b == nil || b.conn == nil {
		return nil, fmt.Errorf("nats connection is nil")
	}
	return b.conn.Subscribe(subject, func(msg *nats.Msg) {
		env, payload, err := decodeEnvelope(b.secret, subject, msg.Data)
		if err != nil {
			log.Printf("nats envelope error subject=%s: %v", subject, err)
			return
		}
		if deduper != nil {
			claimed, err := deduper.ClaimMessage(ctx, subject, env.MessageID, env.Issuer, env.IssuedAt)
			if err != nil {
				log.Printf("nats claim error subject=%s id=%s: %v", subject, env.MessageID, err)
				return
			}
			if !claimed {
				log.Printf("nats duplicate dropped subject=%s id=%s", subject, env.MessageID)
				return
			}
		} else if b.seenMessage(env.MessageID, env.IssuedAt) {
			log.Printf("nats duplicate dropped subject=%s id=%s", subject, env.MessageID)
			return
		}
		if err := handler(payload); err != nil {
			log.Printf("nats handler error subject=%s: %v", subject, err)
		}
	})
}

func signEnvelope(secret []byte, messageID, subject, issuer string, issuedAt int64, payload []byte) string {
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write([]byte(messageID))
	_, _ = mac.Write([]byte("|"))
	_, _ = mac.Write([]byte(subject))
	_, _ = mac.Write([]byte("|"))
	_, _ = mac.Write([]byte(issuer))
	_, _ = mac.Write([]byte("|"))
	_, _ = mac.Write([]byte(fmt.Sprintf("%d", issuedAt)))
	_, _ = mac.Write([]byte("|"))
	_, _ = mac.Write(payload)
	return base64.StdEncoding.EncodeToString(mac.Sum(nil))
}

func decodeEnvelope(secret []byte, expectedSubject string, data []byte) (envelope, []byte, error) {
	var env envelope
	if err := json.Unmarshal(data, &env); err != nil {
		return envelope{}, nil, err
	}
	if env.Subject != expectedSubject {
		return envelope{}, nil, fmt.Errorf("unexpected subject %q", env.Subject)
	}
	if expectedIssuer := issuerForSubject(expectedSubject); expectedIssuer != "" && env.Issuer != expectedIssuer {
		return envelope{}, nil, fmt.Errorf("unexpected issuer %q", env.Issuer)
	}
	if env.MessageID == "" {
		return envelope{}, nil, fmt.Errorf("missing messageId")
	}
	if env.IssuedAt == 0 {
		return envelope{}, nil, fmt.Errorf("missing issuedAt")
	}
	age := time.Since(time.Unix(env.IssuedAt, 0))
	if age < -5*time.Minute || age > time.Hour {
		return envelope{}, nil, fmt.Errorf("stale envelope")
	}
	expected := signEnvelope(secret, env.MessageID, env.Subject, env.Issuer, env.IssuedAt, env.Payload)
	if !hmac.Equal([]byte(expected), []byte(env.Signature)) {
		return envelope{}, nil, fmt.Errorf("invalid signature")
	}
	return env, env.Payload, nil
}

func (b *Bus) seenMessage(messageID string, issuedAt int64) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	cutoff := time.Now().UTC().Add(-2 * time.Hour).Unix()
	for id, ts := range b.seen {
		if ts < cutoff {
			delete(b.seen, id)
		}
	}
	if _, ok := b.seen[messageID]; ok {
		return true
	}
	b.seen[messageID] = issuedAt
	return false
}

func issuerForSubject(subject string) string {
	switch subject {
	case "voice.events":
		return "gateway"
	case "session.closed":
		return "tracker"
	case "session.summary":
		return "writer"
	default:
		return ""
	}
}
