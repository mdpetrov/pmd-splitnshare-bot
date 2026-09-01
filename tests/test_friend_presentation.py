from uuid import uuid4

from splitnshare.application.dto import FriendDTO, GuestDTO
from splitnshare.domain.enums import (
    FriendSource,
    GuestCreationMethod,
    Language,
    PersonKind,
)
from splitnshare.presentation.keyboards import (
    friend_detail_keyboard,
    friends_list_keyboard,
    guests_keyboard,
)
from splitnshare.presentation.routers.people import _friends_text, _guests_text


def test_friends_screen_unifies_registered_and_unregistered_friends() -> None:
    registered = FriendDTO(
        person_id=uuid4(),
        display_name="Alice & Bob",
        kind=PersonKind.USER,
        registered=True,
        source=FriendSource.DIRECT,
        username="alice<",
    )
    unregistered = FriendDTO(
        person_id=uuid4(),
        display_name="Alex",
        kind=PersonKind.GUEST,
        registered=False,
        source=FriendSource.DIRECT,
        username="work_alex",
        alias="Work Alex",
    )

    text = _friends_text((registered, unregistered), Language.ENGLISH)
    keyboard = friends_list_keyboard((registered, unregistered), Language.ENGLISH)

    assert "• Alice &amp; Bob (@alice&lt;)" in text
    assert "• Work Alex (@work_alex · #" in text
    assert "guest" not in text.casefold()
    assert keyboard.inline_keyboard[0][0].callback_data == (
        f"friend:view:{registered.person_id}"
    )
    assert keyboard.inline_keyboard[1][0].callback_data == (
        f"friend:view:{unregistered.person_id}"
    )


def test_guests_screen_lists_guest_names() -> None:
    guest = GuestDTO(
        person_id=uuid4(),
        display_name="Guest <One>",
        creation_method=GuestCreationMethod.MANUAL,
        suggested_telegram_user_id=None,
    )

    text = _guests_text((guest,), Language.ENGLISH)

    assert "• Guest &lt;One&gt;" in text


def test_friend_detail_menu_offers_rename_and_removal() -> None:
    person_id = uuid4()
    friend = FriendDTO(
        person_id=person_id,
        display_name="Alice",
        kind=PersonKind.USER,
        registered=True,
        source=FriendSource.DIRECT,
        username="alice",
    )
    details = friend_detail_keyboard(friend, Language.ENGLISH)

    assert details.inline_keyboard[0][0].callback_data == (
        f"friend:rename:{person_id}"
    )
    assert details.inline_keyboard[0][1].callback_data == (
        f"friend:remove_ask:d:{person_id}"
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
