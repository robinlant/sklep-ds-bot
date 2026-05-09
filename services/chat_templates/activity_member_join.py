from __future__ import annotations


def render(*, member_label: str) -> dict[str, object]:
    return {
        "title": "Member Joined",
        "description": f"Member: {member_label}",
        "color": 0x2ECC71,
        "footer": "Voice Tracker Activity",
    }

