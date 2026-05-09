from __future__ import annotations


def render(*, description: str, page: int, total_pages: int, total_members: int) -> dict[str, object]:
    return {
        "title": "Ranking Top",
        "description": description,
        "color": 0x2B2D42,
        "footer": f"Page {page} of {total_pages} - Total members: {total_members}",
    }

