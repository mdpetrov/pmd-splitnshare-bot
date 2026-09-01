from html import escape
from uuid import UUID

from splitnshare.application.dto import FriendDTO


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


def friend_label(friend: FriendDTO) -> str:
    display_name = friend.alias or friend.display_name
    if friend.registered:
        return participant_label(display_name, friend.person_id, friend.username)
    normalized_username = (friend.username or "").strip().lstrip("@")
    short_code = f"#{friend.person_id.hex[:6]}"
    if normalized_username:
        return f"{display_name} (@{normalized_username} · {short_code})"
    return f"{display_name} ({short_code})"


def friend_html(friend: FriendDTO) -> str:
    return escape(friend_label(friend))
