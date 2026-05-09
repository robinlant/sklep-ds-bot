from __future__ import annotations


def render(*, member_label: str) -> dict[str, object]:
    return {
        "title": "Member Left",
        "description": f"Member: {member_label}",
        "color": 0xE74C3C,
        "footer": "Voice Tracker Activity",
    }

