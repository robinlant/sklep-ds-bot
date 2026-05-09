from __future__ import annotations


def render(
    *,
    member_label: str,
    attribution_status: str,
    invite_code: str,
    invite_url: str,
    actor_label: str,
    exact_status_value: str,
) -> dict[str, object]:
    status = attribution_status or "unknown"
    if status == exact_status_value:
        description = (
            f"Member: {member_label}\n"
            f"Code: `{invite_code or 'unknown'}`\n"
            f"URL: {invite_url or 'unknown'}\n"
            f"Inviter: {actor_label}\n"
            f"Attribution: {status}"
        )
    else:
        description = f"Member: {member_label}\nAttribution: {status}"
    return {
        "title": "Invite Used",
        "description": description,
        "color": 0x9B59B6,
        "footer": "Voice Tracker Activity",
    }

