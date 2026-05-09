from __future__ import annotations


def render(*, invite_code: str, invite_url: str, actor_label: str) -> dict[str, object]:
    return {
        "title": "Invite Deleted",
        "description": (
            f"Code: `{invite_code or 'unknown'}`\n"
            f"URL: {invite_url or 'unknown'}\n"
            f"Deleted invite actor: {actor_label}"
        ),
        "color": 0xE67E22,
        "footer": "Voice Tracker Activity",
    }

