from __future__ import annotations


def render(*, message: str, color: int) -> dict[str, object]:
    return {
        "title": "Voice Session Summary",
        "description": message,
        "color": color,
        "footer": "Voice Tracker",
    }

