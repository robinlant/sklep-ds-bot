from __future__ import annotations

import json


def render(*, payload: dict[str, object]) -> dict[str, object]:
    return {
        "title": "Activity Event",
        "description": json.dumps(payload, ensure_ascii=False),
        "color": 0x5865F2,
        "footer": "Voice Tracker Activity",
    }

