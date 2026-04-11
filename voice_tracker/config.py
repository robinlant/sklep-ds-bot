from __future__ import annotations

import os

from .runtime import Config, load_config, parse_user_ids


def load() -> Config:
    return load_config()


def getenv(key: str, fallback: str) -> str:
    value = os.getenv(key, "").strip()
    return value or fallback
