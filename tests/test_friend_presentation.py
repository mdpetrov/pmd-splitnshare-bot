from uuid import uuid4

from splitnshare.application.dto import FriendDTO, GuestDTO
from splitnshare.domain.enums import (
    FriendSource,
    GuestCreationMethod,
    Language,
    PersonKind,
)
from splitnshare.presentation.keyboards import (
    guests_keyboard,
    registered_friends_keyboard,
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


def test_friend_keyboards_offer_removal_for_active_entries() -> None:
    person_id = uuid4()
    friend = FriendDTO(
        person_id=person_id,
        display_name="Alice",
        kind=PersonKind.USER,
        registered=True,
        source=FriendSource.DIRECT,
        username="alice",
    )
    guest = GuestDTO(
        person_id=person_id,
        display_name="Guest",
        creation_method=GuestCreationMethod.MANUAL,
        suggested_telegram_user_id=None,
    )

    registered = registered_friends_keyboard((friend,), Language.ENGLISH)
    guests = guests_keyboard((guest,), Language.ENGLISH, {person_id})

    assert registered.inline_keyboard[0][0].callback_data == (
        f"friend:remove_ask:r:{person_id}"
    )
    assert guests.inline_keyboard[0][1].callback_data == (
        f"friend:remove_ask:g:{person_id}"
    )


def test_guests_screen_explains_transfer_and_offers_registered_suggestion() -> None:
    guest_id = uuid4()
    target_id = uuid4()
    guest = GuestDTO(
        person_id=guest_id,
        display_name="Guest Alice",
        creation_method=GuestCreationMethod.TELEGRAM,
        suggested_telegram_user_id=9001,
        username="guest_alice",
        suggested_target_person_id=target_id,
        suggested_target_name="Registered Alice",
        suggested_target_username="alice",
    )

    text = _guests_text((guest,), Language.ENGLISH)
    keyboard = guests_keyboard((guest,), Language.ENGLISH)

    assert "temporary participant identity" in text
    assert "Nothing was transferred automatically" in text
    assert "Registered Alice (@alice)" in text
    assert keyboard.inline_keyboard[0][0].callback_data == (
        f"guest:transfer_hint:{guest_id}"
    )
    assert keyboard.inline_keyboard[1][0].callback_data == f"guest:transfer:{guest_id}"
