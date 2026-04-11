from __future__ import annotations

import re

from .discord_models import InteractionCreate


def is_allowlisted(interaction: InteractionCreate | None, allowed_user_ids: list[str] | tuple[str, ...]) -> bool:
    user_id = normalize_user_id(interaction_user_id(interaction))
    if not user_id or len(allowed_user_ids) == 0:
        return False
    for allowed_user_id in allowed_user_ids:
        if normalize_user_id(allowed_user_id) == user_id:
            return True
    return False


def parse_user_ids(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    tokens = [token for token in re.split(r"[\s,;]+", raw) if token]
    seen: set[str] = set()
    ids: list[str] = []
    for token in tokens:
        user_id = normalize_user_id(token)
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        ids.append(user_id)
    return ids


def interaction_user_id(interaction: InteractionCreate | None) -> str:
    if interaction is None:
        return ""
    if interaction.member is not None and interaction.member.user is not None:
        return interaction.member.user.id.strip()
    if interaction.user is not None:
        return interaction.user.id.strip()
    return ""


def normalize_user_id(value: str) -> str:
    value = (value or "").strip()
    for prefix in ("<@!", "<@", "<"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if value.endswith(">"):
        value = value[:-1]
    return value.strip()
