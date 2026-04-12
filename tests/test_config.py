import pytest

from voice_tracker.runtime import load_config


def test_load_bot_admin_user_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_ADMIN_USER_IDS", "<@123>, 456\n<@!789>")

    cfg = load_config()

    assert cfg.bot_admin_user_ids == ["123", "456", "789"]


def test_load_defaults_tracking_mode_specific_when_channels_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRACKING_MODE", raising=False)
    monkeypatch.setenv("TRACKED_CHANNEL_IDS", "c2, c1, c2")

    cfg = load_config()

    assert cfg.tracking_mode == "specific"
    assert cfg.tracked_channel_ids == ["c2", "c1", "c2"]


def test_load_uses_defaults_when_env_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URI", "")
    monkeypatch.setenv("MONGO_DB", "")
    monkeypatch.setenv("NATS_URL", "")

    cfg = load_config()

    assert cfg.mongo_uri == "mongodb://localhost:27017"
    assert cfg.mongo_db == "voice_tracker"
    assert cfg.nats_url == "nats://localhost:4222"
