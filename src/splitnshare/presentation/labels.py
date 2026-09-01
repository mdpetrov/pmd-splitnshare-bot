from html import escape
from uuid import UUID


def participant_label(
    display_name: str, person_id: UUID, username: str | None = None
) -> str:
    normalized_username = (username or "").strip().lstrip("@")
    if normalized_username:
        return f"{display_name} (@{normalized_username})"
    return f"{display_name} (#{person_id.hex[:6]})"


def participant_html(
    display_name: str, person_id: UUID, username: str | None = None
) -> str:
    return escape(participant_label(display_name, person_id, username))
