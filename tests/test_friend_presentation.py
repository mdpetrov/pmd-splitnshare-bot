from uuid import uuid4

from splitnshare.application.dto import FriendDTO, GuestDTO
from splitnshare.domain.enums import (
    FriendSource,
    GuestCreationMethod,
    Language,
    PersonKind,
)
from splitnshare.presentation.routers.people import _friends_text, _guests_text


def test_friends_screen_lists_registered_friends() -> None:
    friend = FriendDTO(
        person_id=uuid4(),
        display_name="Alice & Bob",
        kind=PersonKind.USER,
        registered=True,
        source=FriendSource.DIRECT,
        username="alice<",
    )

    text = _friends_text((friend,), guest_count=2, language=Language.ENGLISH)

    assert "Registered friends: <b>1</b>" in text
    assert "Active guests: <b>2</b>" in text
    assert "• Alice &amp; Bob (@alice&lt;)" in text


def test_guests_screen_lists_guest_names() -> None:
    guest = GuestDTO(
        person_id=uuid4(),
        display_name="Guest <One>",
        creation_method=GuestCreationMethod.MANUAL,
        suggested_telegram_user_id=None,
    )

    text = _guests_text((guest,), Language.ENGLISH)

    assert "• Guest &lt;One&gt;" in text
