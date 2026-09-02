from uuid import uuid4

from splitnshare.application.dto import BalanceDTO, FriendDTO, GuestDTO
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
from splitnshare.presentation.routers.people import (
    _friend_details_text,
    _friends_text,
    _guests_text,
)


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
    assert keyboard.inline_keyboard[-1][0].callback_data == "menu:show"


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


def test_friend_details_show_transaction_count_and_currency_balances() -> None:
    person_id = uuid4()
    friend = FriendDTO(
        person_id=person_id,
        display_name="Alice",
        kind=PersonKind.USER,
        registered=True,
        source=FriendSource.DIRECT,
        username="alice",
    )
    balances = (
        BalanceDTO(person_id, "Alice", "EUR", -1250, "alice"),
        BalanceDTO(person_id, "Alice", "USD", 800, "alice"),
    )

    text = _friend_details_text(
        friend,
        None,
        Language.ENGLISH,
        transaction_count=7,
        balances=balances,
    )

    assert "Shared transactions: <b>7</b>" in text
    assert "🔴 ▼ You owe <b>12.50 EUR</b>" in text
    assert "🟢 ▲ You are owed <b>8.00 USD</b>" in text


def test_friend_details_show_settled_up_when_balance_is_empty() -> None:
    friend = FriendDTO(
        person_id=uuid4(),
        display_name="Alice",
        kind=PersonKind.USER,
        registered=True,
        source=FriendSource.DIRECT,
    )

    text = _friend_details_text(friend, None, Language.ENGLISH)

    assert "Shared transactions: <b>0</b>" in text
    assert "You are settled up." in text


def test_unregistered_friend_detail_restores_explicit_transfer() -> None:
    guest_id = uuid4()
    target_id = uuid4()
    friend = FriendDTO(
        person_id=guest_id,
        display_name="Temporary Alice",
        kind=PersonKind.GUEST,
        registered=False,
        source=FriendSource.DIRECT,
        username="alice",
    )
    guest = GuestDTO(
        person_id=guest_id,
        display_name="Temporary Alice",
        creation_method=GuestCreationMethod.TELEGRAM,
        suggested_telegram_user_id=9002,
        username="alice",
        suggested_target_person_id=target_id,
        suggested_target_name="Registered Alice",
        suggested_target_username="alice",
    )

    text = _friend_details_text(friend, guest, Language.ENGLISH)
    details = friend_detail_keyboard(friend, Language.ENGLISH, guest)

    assert "temporary participant profile" in text
    assert "Registered Alice (@alice)" in text
    assert details.inline_keyboard[1][0].callback_data == (
        f"guest:transfer_hint:{guest_id}"
    )
    assert "Transfer history to Registered Alice (@alice)" in (
        details.inline_keyboard[1][0].text
    )

    manual_guest = GuestDTO(
        person_id=guest_id,
        display_name="Temporary Alice",
        creation_method=GuestCreationMethod.MANUAL,
        suggested_telegram_user_id=None,
    )
    manual_details = friend_detail_keyboard(
        friend, Language.ENGLISH, manual_guest
    )
    assert manual_details.inline_keyboard[1][0].callback_data == (
        f"guest:transfer:{guest_id}"
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

    assert "temporary participant profile" in text
    assert "transfers automatically when that account registers" in text
    assert "if its automatic transfer was not completed" in text
    assert "Registered Alice (@alice)" in text
    assert keyboard.inline_keyboard[0][0].callback_data == (
        f"guest:transfer_hint:{guest_id}"
    )
    assert keyboard.inline_keyboard[1][0].callback_data == f"guest:transfer:{guest_id}"
