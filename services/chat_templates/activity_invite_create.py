from __future__ import annotations


def render(*, invite_code: str, invite_url: str, actor_label: str) -> dict[str, object]:
    return {
        "title": "Invite Created",
        "description": (
            f"Code: `{invite_code or 'unknown'}`\n"
            f"URL: {invite_url or 'unknown'}\n"
            f"Created by: {actor_label}"
        ),
        "color": 0x3498DB,
        "footer": "Voice Tracker Activity",
    }

